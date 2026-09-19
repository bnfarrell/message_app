def test_all_channel_is_auto_created_and_listed(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    rows = agent.get(base).get_json()
    all_channel = next(r for r in rows if r["kind"] == "all")
    assert all_channel["displayName"] == "#ALL"
    assert fx.agent_a.id in [p["userId"] for p in all_channel["participants"]]
    # A second staff member's first request also sees it and is auto-joined.
    eng = login("engineer@hvh.test")
    rows2 = eng.get(base).get_json()
    all_2 = next(r for r in rows2 if r["kind"] == "all")
    assert fx.engineer_a.id in [p["userId"] for p in all_2["participants"]]


def test_create_dm_dedupes_to_existing_thread(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    first = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id})
    assert first.status_code == 201
    conv = first.get_json()
    assert conv["kind"] == "dm" and conv["otherUserId"] == fx.engineer_a.id
    second = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id})
    assert second.status_code == 200
    assert second.get_json()["id"] == conv["id"]
    # The other side sees the same thread too, with otherUserId flipped to the agent.
    eng = login("engineer@hvh.test")
    eng_view = eng.get(f"{base}/{conv['id']}")
    assert eng_view.status_code == 200
    assert eng_view.get_json()["otherUserId"] == fx.agent_a.id


def test_create_group_includes_creator_and_is_visible_to_members(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    sup = login("supervisor@hvh.test")
    res = sup.post(base, json={"kind": "group", "name": "Engineering huddle",
                               "userIds": [fx.engineer_a.id, fx.housekeeper_a.id]})
    assert res.status_code == 201
    group = res.get_json()
    assert group["kind"] == "group" and group["displayName"] == "Engineering huddle"
    member_ids = {p["userId"] for p in group["participants"]}
    assert member_ids == {fx.supervisor_a.id, fx.engineer_a.id, fx.housekeeper_a.id}
    eng = login("engineer@hvh.test")
    listed = eng.get(base).get_json()
    assert group["id"] in [r["id"] for r in listed]


def test_non_participant_gets_404(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    conv = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id}).get_json()
    outsider = login("supervisor@hvh.test")
    assert outsider.get(f"{base}/{conv['id']}").status_code == 404


def test_cross_property_isolation(app, fx, client, database, login):
    base_a = f"/api/p/{fx.property_a.id}/staff-conversations"
    base_b = f"/api/p/{fx.property_b.id}/staff-conversations"
    agent_a = login("agent@hvh.test")
    agent_b = login("agent@lsi.test")
    ids_a = {r["id"] for r in agent_a.get(base_a).get_json()}
    ids_b = {r["id"] for r in agent_b.get(base_b).get_json()}
    assert ids_a.isdisjoint(ids_b)  # the two #ALL channels are different rows
    assert agent_b.get(base_a).status_code == 403  # no membership at property A at all


def test_directory_excludes_self_and_includes_role_department(app, fx, client, database, login):
    agent = login("agent@hvh.test")
    rows = agent.get(f"/api/p/{fx.property_a.id}/staff-directory").get_json()
    ids = {r["userId"] for r in rows}
    assert fx.agent_a.id not in ids
    eng = next(r for r in rows if r["userId"] == fx.engineer_a.id)
    assert eng["role"] == "dept_staff" and eng["departmentName"] == "Engineering"


def test_send_message_updates_list_and_unread(app, fx, client, database, login, events):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    eng = login("engineer@hvh.test")
    conv = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id}).get_json()
    send = agent.post(f"{base}/{conv['id']}/messages", data={"body": "AC in 412 is out"})
    assert send.status_code == 201
    msg = send.get_json()
    assert msg["body"] == "AC in 412 is out" and msg["authorName"] == "Ava Agent"
    assert any(e.type == "staff_message.created" for e in events)

    listed = eng.get(base).get_json()
    row = next(r for r in listed if r["id"] == conv["id"])
    assert row["unread"] is True and row["lastMessagePreview"] == "AC in 412 is out"

    eng.post(f"{base}/{conv['id']}/read")
    listed_after = eng.get(base).get_json()
    row_after = next(r for r in listed_after if r["id"] == conv["id"])
    assert row_after["unread"] is False

    # The sender was never unread on their own message.
    sender_view = agent.get(base).get_json()
    sender_row = next(r for r in sender_view if r["id"] == conv["id"])
    assert sender_row["unread"] is False


def test_send_message_notifies_other_participants(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    conv = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id}).get_json()
    agent.post(f"{base}/{conv['id']}/messages", data={"body": "ping"})
    eng = login("engineer@hvh.test")
    notes = eng.get(f"/api/p/{fx.property_a.id}/notifications").get_json()
    assert any(n["type"] == "staff_message" and n["entityId"] == conv["id"] for n in notes)


def test_send_message_requires_body_or_photo(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    conv = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id}).get_json()
    res = agent.post(f"{base}/{conv['id']}/messages", data={})
    assert res.status_code == 400


def test_non_participant_cannot_send_or_read(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    conv = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id}).get_json()
    outsider = login("supervisor@hvh.test")
    assert outsider.post(f"{base}/{conv['id']}/messages",
                         data={"body": "hi"}).status_code == 404
    assert outsider.post(f"{base}/{conv['id']}/read").status_code == 404


def test_all_channel_message_reaches_every_member(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    admin = login("admin@hvh.test")
    all_channel = next(r for r in admin.get(base).get_json() if r["kind"] == "all")
    admin.post(f"{base}/{all_channel['id']}/messages", data={"body": "Welcome"})
    eng = login("engineer@hvh.test")
    listed = eng.get(base).get_json()
    row = next(r for r in listed if r["kind"] == "all")
    assert row["unread"] is True and row["lastMessagePreview"] == "Welcome"


def test_group_rename_add_and_remove_participant(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    sup = login("supervisor@hvh.test")
    group = sup.post(base, json={"kind": "group", "name": "Eng team",
                                 "userIds": [fx.engineer_a.id]}).get_json()
    renamed = sup.patch(f"{base}/{group['id']}", json={"name": "Engineering"})
    assert renamed.status_code == 200 and renamed.get_json()["displayName"] == "Engineering"

    added = sup.post(f"{base}/{group['id']}/participants",
                     json={"userIds": [fx.housekeeper_a.id]})
    assert added.status_code == 200
    member_ids = {p["userId"] for p in added.get_json()["participants"]}
    assert fx.housekeeper_a.id in member_ids

    hk = login("housekeeper@hvh.test")
    assert hk.get(f"{base}/{group['id']}").status_code == 200  # newly added member can see it

    removed = sup.delete(f"{base}/{group['id']}/participants/{fx.housekeeper_a.id}")
    assert removed.status_code == 200
    assert fx.housekeeper_a.id not in {p["userId"] for p in removed.get_json()["participants"]}
    assert hk.get(f"{base}/{group['id']}").status_code == 404  # removed member loses access


def test_all_channel_rejects_rename_and_remove(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    admin = login("admin@hvh.test")
    all_channel = next(r for r in admin.get(base).get_json() if r["kind"] == "all")
    assert admin.patch(f"{base}/{all_channel['id']}",
                       json={"name": "renamed"}).status_code == 400
    assert admin.delete(
        f"{base}/{all_channel['id']}/participants/{fx.engineer_a.id}"
    ).status_code == 400


def test_all_channel_add_participants_is_noop(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    admin = login("admin@hvh.test")
    all_channel = next(r for r in admin.get(base).get_json() if r["kind"] == "all")
    before_ids = {p["userId"] for p in all_channel["participants"]}
    assert fx.housekeeper_a.id not in before_ids  # hasn't opened Messages yet, so not auto-joined

    res = admin.post(f"{base}/{all_channel['id']}/participants",
                     json={"userIds": [fx.housekeeper_a.id]})
    assert res.status_code == 200
    after_ids = {p["userId"] for p in res.get_json()["participants"]}
    assert after_ids == before_ids  # no-op: membership in #ALL is automatic, not manually added


def test_dm_rejects_rename_and_participant_changes(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    conv = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id}).get_json()
    assert agent.patch(f"{base}/{conv['id']}", json={"name": "x"}).status_code == 400
    assert agent.post(f"{base}/{conv['id']}/participants",
                      json={"userIds": [fx.housekeeper_a.id]}).status_code == 400


JPEG_BYTES = b"\xff\xd8\xff" + b"\x00" * 100


def test_send_photo_only_message_and_fetch_it(app, fx, client, database, login):
    from io import BytesIO
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    conv = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id}).get_json()
    res = agent.post(f"{base}/{conv['id']}/messages",
                     data={"photo": (BytesIO(JPEG_BYTES), "room.jpg")},
                     content_type="multipart/form-data")
    assert res.status_code == 201
    msg = res.get_json()
    assert msg["body"] is None and msg["photoUrl"]
    eng = login("engineer@hvh.test")
    fetched = eng.get(msg["photoUrl"])
    assert fetched.status_code == 200 and fetched.data == JPEG_BYTES
    outsider = login("supervisor@hvh.test")
    assert outsider.get(msg["photoUrl"]).status_code == 404


def test_photo_rejects_bad_type_and_oversize(app, fx, client, database, login):
    from io import BytesIO
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    conv = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id}).get_json()
    bad_type = agent.post(f"{base}/{conv['id']}/messages",
                          data={"photo": (BytesIO(b"not an image"), "x.jpg")},
                          content_type="multipart/form-data")
    assert bad_type.status_code == 400
