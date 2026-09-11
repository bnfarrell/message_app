# G1 report — the server half of the disclosed-gap fixes

Three commits on `main`, one per item, as briefed:

| sha | item |
| --- | --- |
| `da6d4ad` | analytics buckets in the property's timezone |
| `65cf4d1` | the seed's self-contradictions |
| `38984a1` | work-order photo upload |

Server suite **348 → 361**, `ruff check .` clean. Web suite 539 passed, `tsc --noEmit` and
`npm run lint` clean (see "The client change I did have to make").

A dev server was already listening on 127.0.0.1:5200 when I started — I checked before doing
anything and never started one. It had stopped by the end of the session; I did not restart it,
and I never touched `dev_start.py`'s guard.

---

## 1. Timezone bucketing

`app/domain/analytics.py`. `overview()` now resolves the property's own IANA zone once and
converts each inbound `sent_at` before taking `.hour` / `.date()`:

```python
zone = property_zone(db, property_id)          # Property.timezone, validated on write
local_inbound = [local(m.sent_at, zone) for m in inbound]
```

**Why it cannot double-apply.** `since`/`until` are untouched. They are UTC instants that decide
*which messages are in range*; the zone decides *which bucket* a message in range falls into.
Those are two different questions and only the second one moved. `test_range_filter_is_not_shifted_by_the_bucket_timezone`
mutation-tests exactly that: shifting the window boundaries as well makes it fail (and takes
`test_overview_excludes_other_property_data` down with it).

**Naive-datetime care.** I verified rather than assumed: `app.db.UTCDateTime.process_result_value`
attaches UTC, and it does so even for a column-level select (`select(Message.sent_at)`), which is
the shape `overview()` uses — checked against a real row. `local()` still attaches UTC explicitly
when `tzinfo` is absent, because the failure mode if it ever is naive is `astimezone()` silently
reading the *server machine's* zone: a wrong answer that is invisible on a UTC host and wrong
everywhere else. One expression, and it is the difference between a loud bug and a silent one.

**A defect in the existing test, not in the brief.** `test_overview_and_agents` asserted
`hour_counts[start.hour]` and a two-element `inboundByDay` — i.e. it asserted the UTC bucketing,
the bug itself. Its two messages are 13h apart and straddle UTC midnight, so under the fix they
are two local hours on **one** local day. I updated it to the true local answer. It is the only
non-seed test that changed, and it was strengthened, not loosened.

Two new tests. `test_buckets_use_each_property_own_timezone` sends one instant
(2026-09-11 01:30 UTC) to both properties and asserts New York reports hour 21 on 2026-09-10 and
Chicago reports hour 20 on 2026-09-10 — different hours, so a single hardcoded offset cannot
satisfy both, and both differ from the UTC answer (hour 1 on the 11th) in hour *and* date.

## 2. The seed

Every number below was queried against a freshly seeded database before and after; none of it is
recalled. All three claims in the brief were true when checked.

**Stay history.** 106 guests, 106 stays, no guest with more than one — confirmed. Meanwhile
`stay_count` was `rng.randint(1, 6)`, so **95 of 106 stays claimed a repeat visit no row backed**
and the panel printed "4th stay" beside an empty Previous-stays list for almost everybody.

Fixing two guests would have left 93 still contradicting themselves, so the repair is the
invariant, not the exception: `stay_count` and `is_return_guest` are no longer random at all. One
pass after every stay exists numbers each guest's stays by arrival date and sets
`is_return_guest = n > 1`, so the denormalised count and the rows cannot disagree for any guest,
now or after a future edit. On top of that, Sarah Chen has three prior stays (Ava's seeded
internal note calls her a "Gold member, 4th stay" — that is now true of the rows) and Tom Becker
has one. Both are guests with a prominent seeded conversation (the showcase thread and the
failed-delivery thread), so the panel section is reachable from the seeded inbox rather than
buried.

`actual_checkout_at` was `now - 20..40h` regardless of the stay's own dates. Roughly right for a
stay that ended yesterday, plainly wrong for one that ended a year ago, so it is now derived from
the departure date. A test asserts `actual_checkout_at.date() == departure_date` for every
checked-out row.

**Lakeside Inn** had zero conversations — confirmed. It now has six in-house stays and four
conversations (two waiting, one answered by Bea, one archived). The archived one deliberately
carries **no** resolution category: every seeded category belongs to Harbourview, and pointing a
Lakeside conversation at one would be a tenancy bug baked into the data.

**A conversation with no stay** (spec §8) — confirmed absent, count was 0. Diego Ruiz now texts
about a future reservation while not in house, so `room_number` is null and quick-reply
interpolation takes its fallback branch.

**Determinism and the reset guard are unchanged.** Still `random.Random(42)`; the
reseed-equality and identical-phone-number tests pass untouched, and `run(reset=True)` still
refuses non-sqlite URLs. Note that removing two `rng` draws from `make_stay` shifts the whole
downstream random sequence, so names and phone numbers differ between the old and the new seed —
they are identical between two runs of the new one, which is what determinism means here.

**Numbers that moved** (all updated to the new true values in `tests/test_seed.py`; nothing was
weakened to a range or an inequality):

| | before | after |
| --- | --- | --- |
| guests | 106 | 110 |
| stays | 106 | 113 |
| HVH checked_out stays | 8 | 12 |
| LSI checked_in stays | 3 | 6 |
| conversations | 30 | 35 |
| — HVH | 30 | 31 |
| — LSI | 0 | 4 |
| messages | 52 | 59 |
| guests with >1 stay | 0 | 2 |
| conversations with no stay | 0 | 1 |

Unchanged and still asserted: 85 checked-in and 10 reserved HVH stays, 5 archived HVH
conversations, 2 draft prompts, 1 opted-out guest, 1 redacted message, 15 active work orders,
8 digital assets, 12 HVH memberships.

I checked the analytics, board and inbox tests before touching anything: **only `tests/test_seed.py`
reads the seed at all.** Every other test builds its own data from `tests/fixtures.py`, so nothing
else could break — and nothing else did.

## 3. Work-order photos — the contract G2 codes against

Storage ruling accepted as written, and I agree with it: the filesystem is ephemeral, a
disk-backed photo disappears on the next redeploy with no error anywhere, and object storage is
out of scope. `LargeBinary` is `BLOB` on SQLite and `BYTEA` on PostgreSQL; the column is
`deferred`, so listing a work order's photos never loads the blobs.

### Accepted types and size cap

| | |
| --- | --- |
| accepted | `image/jpeg`, `image/png`, `image/webp` |
| cap | **8 MiB = 8 388 608 bytes** (`work_orders.MAX_PHOTO_BYTES`) |

Three types, all of which a browser can render — the server hands these bytes straight back for
display, so accepting a format no `<img>` can show would store an image nobody can see. HEIC is
deliberately absent for that reason; iOS uploads a JPEG for `accept="image/*"`.

8 MiB is comfortably above a full-resolution phone JPEG (2–5 MB is typical) with room to spare,
and small enough that a row stays cheap to `SELECT` whole, which matters because neither SQLite
nor psycopg streams the column here.

**The type is sniffed from the bytes; the client's declared `Content-Type` is ignored entirely.**
That is deliberate: the client controls that header, and it is the value the GET route would
otherwise echo back as the response's own `Content-Type`. A WebP labelled `image/jpeg` is stored
and served as `image/webp`; a PDF or a GIF labelled `image/png` is refused. Both are tested.

Set `accept="image/jpeg,image/png,image/webp"` on the input and check `file.size` client-side for
a fast failure, but treat the server as the authority — it re-checks both.

### POST — upload

```
POST /api/p/{propertyId}/work-orders/{workOrderId}/photos
Content-Type: multipart/form-data
```

| part | type | required | value |
| --- | --- | --- | --- |
| `photo` | file | yes | the image bytes |
| `kind` | text | yes | `"before"` or `"after"` |

Send it as a `FormData` and **do not set `Content-Type` yourself** — the browser must add the
boundary. Credentials as usual (cookie session), no extra header.

**201** → a `WorkOrderPhotoOut`:

```json
{
  "id": "5f1c…",
  "workOrderId": "9a20…",
  "kind": "before",
  "contentType": "image/png",
  "byteSize": 48213,
  "uploadedByUserId": "u-eli",
  "uploadedByName": "Eli Engineer",
  "url": "/api/p/{propertyId}/work-orders/{workOrderId}/photos/5f1c…",
  "createdAt": "2026-09-10T18:47:00Z"
}
```

`uploadedByUserId` and `uploadedByName` are nullable in the schema; in practice the route always
has an authenticated actor, so they are populated. `url` is ready to drop into an `<img src>`.

**Errors.** All 400s, per the project contract, never 422. Two `details` shapes, both already
handled by `web/src/api/fieldErrors.ts` — use it, do not write a second normaliser:

| case | status | `details` |
| --- | --- | --- |
| no `photo` part, or an empty file | 400 | `{"photo": "required"}` |
| over 8 MiB | 400 | `{"photo": "file_too_large"}` |
| not a JPEG/PNG/WebP | 400 | `{"photo": "unsupported_image_type"}` |
| `kind` missing or not before/after | 400 | Pydantic **array**; field is `loc[-1]` = `"kind"` |
| work order not found | 404 | — |
| not a member of that property | 403 | — |

The object-shape key `photo` is the form part's name and is already camelCase (one word).

### GET — the bytes

```
GET /api/p/{propertyId}/work-orders/{workOrderId}/photos/{photoId}
```

**200** → the raw image. `Content-Type` is the stored type, plus `Content-Disposition: inline`,
`X-Content-Type-Options: nosniff`, and `Cache-Control: private, max-age=86400` (nothing can
replace a photo once attached, so the bytes at a given id are immutable). **404** for an id that
does not belong to this property *and* this work order; **403** for a non-member.

The route is cookie-authenticated like every other one, so a plain `<img src={photo.url}>` works
as long as the client and API share an origin; cross-origin dev needs `crossOrigin="use-credentials"`
or a fetch-to-blob.

### Reading photos back

`GET /api/p/{pid}/work-orders/{id}` — `WorkOrderDetail` gains:

```ts
photos: WorkOrderPhotoOut[]   // oldest first (created_at, then id)
```

There is **no separate list endpoint**; the detail response is the list. After a successful
upload, invalidate the detail query — `usePatchWorkOrder` already does this for comments and the
same invalidation is what you want here.

### One new timeline event type

`WorkOrderEventType` gains **`photo_attached`**, with `toValue` = `"before"` / `"after"` and
`userName` set, matching the mockup's "Eli · after photo attached · 18:56". The Timeline renderer
must handle this new `type` or the entry will fall through whatever default it has.

### Deletion: not allowed, and there is no route

The mockup shows no delete affordance; a before/after pair is evidence that work was done; and
deciding who may remove one — the uploader, a supervisor, anyone before close? — is invented
behaviour, which is precisely the class of gap the user chose to skip. If it is wanted later it
needs a ruling, not a guess.

### Gating

`@require_auth` + `@require_property`, **no capability gate**. That is not an oversight: `PATCH`
on the same work order carries none either, beyond `close_work_order` for a closing status, so
attaching a photo is gated exactly like leaving a comment on it. Inventing a capability here
would put this route out of step with the one beside it, and would put the client out of step
with the server — the same reasoning as ruling in commit `7640b04`.

Tenancy is not left to the decorator alone. A photo id is a guessable handle, so `get_photo()`
filters on property **and** work order. Tests assert that property B's own admin — who passes
`require_property` for B — gets 404 rather than the image for A's photo id under B's path, and
that a photo does not resolve through a sibling work order in the same property. Both filters are
mutation-tested.

### Acceptance criterion 9 — confirmed, not assumed

`app.url_map` enumeration went 44 → 46 rules under `/api/p/<property_id>`, and I printed them:

```
['POST'] /api/p/<property_id>/work-orders/<work_order_id>/photos
['GET']  /api/p/<property_id>/work-orders/<work_order_id>/photos/<photo_id>
```

`tests/test_isolation.py` therefore walks both automatically (403 cross-property, 401 anonymous,
non-403 for a member of the property).

### Migration 0004

Creates `work_order_photo` and widens the `work_order_event.type` CHECK constraint for
`photo_attached` — the enum is `native_enum=False`, so it is a named CHECK on both dialects.
Verified upgrade → downgrade → upgrade on SQLite (FKs, indexes and the constraint all survive the
batch rebuild), and rendered offline against the PostgreSQL dialect, where it is `BYTEA` plus a
plain `DROP CONSTRAINT` / `ADD CONSTRAINT`. The downgrade deletes `photo_attached` event rows
first, since they would violate the narrowed constraint.

---

## The client change I did have to make

The brief says no client change, and I made none to behaviour — but two files under `web/` are
downstream *artifacts* of the server contract and leaving them stale would have put `main` in the
exact state a previous commit message describes ("main was red on the web suite while the server
suite was green"):

- `web/src/api/schema.json` — regenerated by `python -m app.schemas.export_json_schema`, which
  `tests/test_schema_export.py::test_committed_schema_is_current` requires. Not hand-edited.
- `web/src/api/types.generated.ts` — regenerated by `npm run gen:types`, which
  `web/src/api/types.generated.test.ts` requires. Not hand-edited.
- `web/src/test/factories.ts` — **one line**, `photos: []` added to `aWorkOrderDetail`, beside the
  existing `events: []`. Without it `npm run build` (`tsc -b`) fails, because `photos` is a
  required field of `WorkOrderDetail`. I confirmed this was the *only* type error introduced, so
  `tsc` was clean before and is clean after.

Flagging it rather than burying it. If the reviewer would rather `photos` were optional on the
wire, say so — but the server always sends it, so an optional field would be a lie.

---

## Found but not fixed

1. **`_CURRENT-CONTRACTS.md` is stale on one point.** It says *"Never render `details` verbatim:
   the array shape's `input` key echoes the user's raw typing back."* That is no longer true:
   both `app/api/_util.py` (`parse_body`, `parse_query`) and `errors.register_error_handlers`
   pass `include_input=False`, so `input` is absent from every Pydantic `details` this server
   emits. The advice is still good hygiene; the stated reason no longer applies.

2. **A false comment in `tests/fixtures.py`.** `regional@group.test` is commented "manager at
   both properties" but only one `_member(db, shared, b, Role.manager)` call exists — Riley is a
   member of property B only. There is currently **no fixture user who is a member of both
   properties**, which is why my cross-tenant test uses B's own admin rather than a dual member.
   Not fixed: adding the missing membership would change what `test_isolation`'s walk covers and
   is a decision, not a typo.

3. **`WorkOrderEvent` ordering has no tiebreak.** `detail()` orders events by `created_at` alone,
   so two events written in the same transaction (assign + status change on one PATCH) order
   arbitrarily. This surfaced in my own work: with the clock frozen, two photos uploaded in the
   same test had identical `created_at`. I gave the photo query a `(created_at, id)` tiebreak and
   advanced the clock in the test (the mockup's own photos are nine minutes apart) rather than
   weaken production. The pre-existing event query still has the gap. Not fixed: out of scope,
   and it would need the same care in several existing tests.

4. **Working-tree noise that is not mine.** `server/data/app.db` shows as modified and its
   `-wal`/`-shm` as deleted — the dev SQLite database is *tracked in git*, so every dev-server run
   dirties the tree. `two.png` at the repo root shows as deleted, and three `review-*.diff` files
   in this workspace are untracked. None of these are mine; I staged every commit by explicit path
   and left them exactly as I found them. The tracked dev database in particular is worth a
   ruling: it guarantees a dirty tree after any local run.

5. **The seed's `NOTES` list is generic but assigned per-conversation.** `"Gold member, 4th stay"`
   is `data.NOTES[0]` and can land on any conversation via `rng.choice`, not just Sarah's. Sarah's
   own showcase note is written separately and is now true. The randomly-placed copies may still
   land on a guest with one stay. Not fixed: making every internal note consistent with its
   guest's row count would mean generating note text from data, which is a design change, not a
   repair.

6. **The dev database has not been migrated to 0004.** Nothing to do — `dev_start.prepare()` runs
   `run_migrations` before the server starts, and `tests/conftest.py` migrates its session
   template, so both pick it up automatically on the next run.

---

## Verification

- `python -m pytest -q` in `server/`: **361 passed**, from a measured baseline of 348 at `8c46d1d`
  (the most recent commit message claiming a count says 347; the tree had 348).
- `python -m ruff check .`: clean.
- `npm test` in `web/`: 539 passed. `npx tsc --noEmit`: clean. `npm run lint`: clean.
- **Every production check in this wave was mutation-tested** — reverted in turn to confirm the
  suite reddens without it, and that the *intended* test is the one that fails:

| mutation | caught by |
| --- | --- |
| bucket on raw UTC | 3 analytics tests |
| shift `since`/`until` by the zone too | 3 analytics tests |
| `stay_count` back to random | the stay-history test |
| remove Sarah's and Tom's prior stays | the counts test + the stay-history test |
| `get_photo` drops the property filter | the cross-property read test |
| `get_photo` drops the work-order filter | the sibling-work-order test |
| size cap off by one (`>=`) | the cap test's at-cap case |
| type sniffing bypassed | the PDF/GIF rejection test |
| timeline event not written | the upload round-trip test |
| audit row not written | the upload round-trip test |
| served `Content-Type` hardcoded | the WebP mislabelling test |
| Content-Length guard removed | the oversized-body test |
| `photos` omitted from `WorkOrderDetail` | the upload round-trip test |
