"""Work-order before/after photos (docs/mockups/WorkOrder.dc.html:91-94, 111).

The bytes live in the database, so these tests exercise the round trip through it: upload, read
back byte-for-byte, the timeline event, the audit row, and the tenancy of both routes.
"""
import io

from sqlalchemy import select

from app import clock
from app.domain import work_orders
from app.models import AuditLog, WorkOrderPhoto

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 40
WEBP = b"RIFF" + (60).to_bytes(4, "little") + b"WEBPVP8 " + b"\x00" * 40
GIF = b"GIF89a" + b"\x00" * 40  # a real image, deliberately not accepted
PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n" + b"\x00" * 40


def upload(client, property_id, work_order_id, data, kind="before", filename="photo.png",
           content_type="image/png"):
    return client.post(
        f"/api/p/{property_id}/work-orders/{work_order_id}/photos",
        data={"kind": kind, "photo": (io.BytesIO(data), filename, content_type)},
        content_type="multipart/form-data")


def make_work_order(client, property_id, title="AC not cooling"):
    res = client.post(f"/api/p/{property_id}/work-orders",
                      json={"title": title, "type": "maintenance", "locationRef": "412"})
    assert res.status_code == 201, res.get_json()
    return res.get_json()["id"]


def test_upload_read_back_timeline_and_audit(app, fx, login, database):
    eng = login("engineer@hvh.test")
    wo_id = make_work_order(eng, fx.property_a.id)

    res = upload(eng, fx.property_a.id, wo_id, PNG, kind="before")
    assert res.status_code == 201, res.get_json()
    photo = res.get_json()
    assert photo["kind"] == "before"
    assert photo["contentType"] == "image/png"
    assert photo["byteSize"] == len(PNG)
    assert photo["workOrderId"] == wo_id
    assert photo["uploadedByUserId"] == fx.engineer_a.id
    assert photo["uploadedByName"] == "Eli Engineer"
    assert photo["url"] == (f"/api/p/{fx.property_a.id}/work-orders/{wo_id}"
                            f"/photos/{photo['id']}")

    served = eng.get(photo["url"])
    assert served.status_code == 200
    assert served.data == PNG  # byte-for-byte, not merely non-empty
    assert served.headers["Content-Type"] == "image/png"
    assert served.headers["X-Content-Type-Options"] == "nosniff"

    # The mockup's two photos are nine minutes apart (18:47 before, 18:56 after) and the panel
    # lists them in that order. Without advancing the frozen clock both rows would carry the same
    # created_at and the order would fall through to the uuid tiebreak.
    clock.advance(minutes=9)
    after = upload(eng, fx.property_a.id, wo_id, JPEG, kind="after",
                   filename="done.jpg", content_type="image/jpeg").get_json()
    detail = eng.get(f"/api/p/{fx.property_a.id}/work-orders/{wo_id}").get_json()
    assert [p["id"] for p in detail["photos"]] == [photo["id"], after["id"]]  # oldest first
    assert [p["kind"] for p in detail["photos"]] == ["before", "after"]
    assert [p["contentType"] for p in detail["photos"]] == ["image/png", "image/jpeg"]

    # The mockup's timeline shows "Eli · after photo attached", so each upload is an event.
    attached = [e for e in detail["events"] if e["type"] == "photo_attached"]
    assert [e["toValue"] for e in attached] == ["before", "after"]
    assert {e["userName"] for e in attached} == {"Eli Engineer"}

    with database.session() as db:
        rows = db.scalars(select(AuditLog).where(
            AuditLog.action == "work_order.photo_attached")).all()
        assert [r.entity_id for r in rows] == [photo["id"], after["id"]]
        assert [r.entity_type for r in rows] == ["work_order_photo"] * 2
        assert [r.actor_user_id for r in rows] == [fx.engineer_a.id] * 2
        assert rows[0].after == {"work_order_id": wo_id, "kind": "before",
                                 "content_type": "image/png", "byte_size": len(PNG)}


def test_webp_is_accepted_and_typed_from_its_bytes_not_the_clients_claim(app, fx, login):
    eng = login("engineer@hvh.test")
    wo_id = make_work_order(eng, fx.property_a.id)
    # The client mislabels a WebP as a JPEG. The stored type comes from the bytes.
    res = upload(eng, fx.property_a.id, wo_id, WEBP, filename="x.jpg", content_type="image/jpeg")
    assert res.status_code == 201
    assert res.get_json()["contentType"] == "image/webp"
    assert eng.get(res.get_json()["url"]).headers["Content-Type"] == "image/webp"


def test_a_non_image_labelled_as_one_is_rejected(app, fx, login, database):
    eng = login("engineer@hvh.test")
    wo_id = make_work_order(eng, fx.property_a.id)
    for payload, filename in ((PDF, "invoice.pdf"), (GIF, "animation.gif")):
        res = upload(eng, fx.property_a.id, wo_id, payload, filename=filename,
                     content_type="image/png")  # the client's claim is a lie, or unsupported
        assert res.status_code == 400, res.get_json()
        body = res.get_json()["error"]
        assert body["code"] == "VALIDATION_FAILED"
        assert body["details"] == {"photo": "unsupported_image_type"}
    with database.session() as db:
        assert db.scalars(select(WorkOrderPhoto)).all() == []


def test_a_photo_over_the_cap_is_rejected(app, fx, login, database):
    eng = login("engineer@hvh.test")
    wo_id = make_work_order(eng, fx.property_a.id)
    cap = work_orders.MAX_PHOTO_BYTES
    oversized = PNG + b"\x00" * (cap + 1 - len(PNG))
    assert len(oversized) == cap + 1

    res = upload(eng, fx.property_a.id, wo_id, oversized)
    assert res.status_code == 400, res.status_code
    assert res.get_json()["error"]["details"] == {"photo": "file_too_large"}

    # Exactly at the cap is accepted: the boundary must not be off by one in the other direction.
    at_cap = PNG + b"\x00" * (cap - len(PNG))
    assert upload(eng, fx.property_a.id, wo_id, at_cap).status_code == 201
    with database.session() as db:
        assert [p.byte_size for p in db.scalars(select(WorkOrderPhoto)).all()] == [cap]


def test_an_oversized_body_is_refused_before_it_is_parsed(app, fx, login):
    """The cap above is enforced on the bytes received. This one is the Content-Length guard in
    front of it, which exists so an obviously oversized body is never read at all.

    Distinguished from the byte check by sending no `photo` part and an unknown `junk` field: if
    the guard did not fire, the body would be parsed and the 400 would name `junk` (the upload
    schema forbids unknown fields) rather than the photo.
    """
    eng = login("engineer@hvh.test")
    wo_id = make_work_order(eng, fx.property_a.id)
    res = eng.post(f"/api/p/{fx.property_a.id}/work-orders/{wo_id}/photos",
                   data={"kind": "before",
                         "junk": "x" * (work_orders.MAX_PHOTO_BYTES + 8192)},
                   content_type="multipart/form-data")
    assert res.status_code == 400
    assert res.get_json()["error"]["details"] == {"photo": "file_too_large"}


def test_kind_and_file_are_both_required(app, fx, login):
    eng = login("engineer@hvh.test")
    wo_id = make_work_order(eng, fx.property_a.id)
    base = f"/api/p/{fx.property_a.id}/work-orders/{wo_id}/photos"

    missing_file = eng.post(base, data={"kind": "before"}, content_type="multipart/form-data")
    assert missing_file.status_code == 400
    assert missing_file.get_json()["error"]["details"] == {"photo": "required"}

    missing_kind = eng.post(
        base, data={"photo": (io.BytesIO(PNG), "p.png", "image/png")},
        content_type="multipart/form-data")
    assert missing_kind.status_code == 400
    # Pydantic's array shape; the field is loc[-1], camelCase like every other field error here.
    assert [d["loc"][-1] for d in missing_kind.get_json()["error"]["details"]] == ["kind"]

    bad_kind = upload(eng, fx.property_a.id, wo_id, PNG, kind="during")
    assert bad_kind.status_code == 400
    assert [d["loc"][-1] for d in bad_kind.get_json()["error"]["details"]] == ["kind"]


def test_an_unknown_work_order_is_404_not_an_orphan_photo(app, fx, login, database):
    eng = login("engineer@hvh.test")
    missing = "00000000-0000-0000-0000-000000000000"
    assert upload(eng, fx.property_a.id, missing, PNG).status_code == 404
    with database.session() as db:
        assert db.scalars(select(WorkOrderPhoto)).all() == []


def test_a_photo_cannot_be_read_from_another_property(app, fx, login):
    """A photo id is a guessable handle. Property A's member is 403'd by the route gate; property
    B's own admin, who passes that gate, must still not resolve A's id under B's path."""
    eng = login("engineer@hvh.test")
    wo_id = make_work_order(eng, fx.property_a.id)
    photo = upload(eng, fx.property_a.id, wo_id, PNG).get_json()

    admin_b = login("admin@lsi.test")
    # Same photo, same work order, B's property segment: B has no membership answer for A's data.
    assert admin_b.get(f"/api/p/{fx.property_b.id}/work-orders/{wo_id}"
                       f"/photos/{photo['id']}").status_code == 404
    assert admin_b.post(f"/api/p/{fx.property_b.id}/work-orders/{wo_id}/photos",
                        data={"kind": "before",
                              "photo": (io.BytesIO(PNG), "p.png", "image/png")},
                        content_type="multipart/form-data").status_code == 404
    # And A's own route is 403 for a member of neither-this-property, which is the acceptance
    # criterion 9 walk in tests/test_isolation.py; asserted here on a real id rather than a dummy.
    assert admin_b.get(f"/api/p/{fx.property_a.id}/work-orders/{wo_id}"
                       f"/photos/{photo['id']}").status_code == 403


def test_a_photo_id_is_not_readable_through_a_different_work_order(app, fx, login):
    eng = login("engineer@hvh.test")
    mine = make_work_order(eng, fx.property_a.id, title="AC")
    other = make_work_order(eng, fx.property_a.id, title="Lamp")
    photo = upload(eng, fx.property_a.id, mine, PNG).get_json()
    assert eng.get(f"/api/p/{fx.property_a.id}/work-orders/{other}"
                   f"/photos/{photo['id']}").status_code == 404


def test_sniffing_rejects_a_truncated_riff_container(app, fx, login):
    """`data[8:12]` on a four-byte body must not read as WEBP by accident."""
    assert work_orders.sniff_image_type(b"RIFF") is None
    assert work_orders.sniff_image_type(b"") is None
    assert work_orders.sniff_image_type(b"RIFF" + b"\x00" * 4 + b"WAVE") is None
