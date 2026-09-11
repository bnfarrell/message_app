### Task 24: Dev entrypoint, root scripts, README, final verification

**Files:**
- Create: `server/.env.example`, `package.json` (root), `README.md`
- Modify: `server/run.py`, `server/app/__init__.py` (CORS for the Vite dev server)

**Interfaces:**
- Produces: `npm run server` (Flask dev server on :5000 with worker), `npm run seed`, `npm run test:server`; README with setup, seeded credentials, simulator instructions, Postgres switch. (`npm run dev` and `npm run web` are added by the web plan.)

- [ ] **Step 1: CORS for the SPA dev server**

Vite proxies `/api` and `/ws` to Flask, so no CORS is needed in the intended setup. Add a guard anyway for anyone hitting the API directly from `http://localhost:5173`: in `create_app`, after blueprints:
```python
    @app.after_request
    def _cors(resp):
        origin = request.headers.get("Origin")
        if origin and origin == config.CORS_ORIGIN:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Mock-Secret"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        return resp
```
with `from flask import request` at the top of `app/__init__.py`.

- [ ] **Step 2: Finish `run.py` and add `.env.example`**

`server/run.py`:
```python
"""Development entrypoint. Production: gunicorn -k gthread -w 1 --threads 16 'app:create_app()'"""
import os

from app import create_app
from app.config import Config

if __name__ == "__main__":
    os.environ.setdefault("START_WORKER", "1")
    cfg = Config.from_env()
    app = create_app(cfg)
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=not cfg.is_production, threaded=True)
```

`server/.env.example`:
```
FLASK_ENV=development
PORT=5000
DATABASE_URL=sqlite:///data/app.db
SESSION_SECRET=change-me-in-production
MOCK_SMS_SECRET=dev
SMS_ADAPTER=mock
PMS_TICK_SECONDS=90
START_WORKER=1
CORS_ORIGIN=http://localhost:5173
```

- [ ] **Step 3: Root `package.json`**

```json
{
  "name": "concierge",
  "private": true,
  "scripts": {
    "server": "cd server && python run.py",
    "seed": "cd server && python -m seed.seed",
    "test:server": "cd server && python -m pytest -q",
    "schema": "cd server && python -m app.schemas.export_json_schema"
  }
}
```
(These assume the venv is activated in the shell running npm; the README says so. The web plan adds `web`, `dev` via `concurrently`, and `gen:types`.)

- [ ] **Step 4: README**

`README.md`:
```markdown
# Concierge — hotel guest engagement & operations (Phase 1)

One codebase, one database: guests text the hotel; staff answer from a shared inbox; problems become work
orders; when the work order closes, the agent is prompted to tell the guest. Spec: `docs/design.md`.
Phase 1 scope and stack decisions: `docs/superpowers/specs/2026-09-10-hotel-engagement-phase1-design.md`.
Approved screens: `docs/mockups/` (Night Shift direction).

## Stack
Python 3.12+ · Flask 3 · SQLAlchemy 2 · Alembic · Pydantic v2 · flask-sock · pytest — SQLite now, PostgreSQL by
changing `DATABASE_URL`. Frontend: Vite + React + TypeScript (see the web plan).

## Setup (Windows / macOS / Linux)
```bash
python -m venv .venv
# Windows Git Bash: . .venv/Scripts/activate   PowerShell: .venv\Scripts\Activate.ps1   macOS/Linux: . .venv/bin/activate
cd server && pip install -e ".[dev]" && cd ..
cp server/.env.example server/.env
npm run seed          # creates server/data/app.db with realistic data
npm run server        # http://127.0.0.1:5000  (API + WebSocket + job worker)
npm run test:server   # pytest, including the §11.1 acceptance suite
```
Note: npm ≥ 11.19 blocks package install scripts by default; the server has no native dependencies, so this
does not affect the Python side. If a Node package needs its install script, run `npm install-scripts approve <pkg>`.

## Seeded logins (password for all: `Password123!`)
| Email | Role | Lands on |
|---|---|---|
| ava@hvh.test, marcus@hvh.test, jordan@hvh.test | agent | Inbox |
| eli@hvh.test, noah@hvh.test | dept_staff (Engineering) | Board · mine |
| hana@hvh.test, rosa@hvh.test | dept_staff (Housekeeping) | Board · mine |
| sam@hvh.test (Engineering), hk.supervisor@hvh.test (Housekeeping) | supervisor | Board |
| morgan@hvh.test | manager | Analytics |
| alex@hvh.test | admin | Analytics |
| casey@group.test | corporate (HVH + LSI) | Analytics |
| blake@lsi.test / bea@lsi.test | Lakeside Inn admin / agent | — |

## Texting the hotel without Twilio
The SMS wire is mocked (`SMS_ADAPTER=mock`). Send an inbound text exactly as Twilio would:
```bash
curl -X POST http://127.0.0.1:5000/api/hooks/sms/inbound -H "X-Mock-Secret: dev" \
  -d From=+15551234567 -d To=+15550100 -d "Body=The AC in 412 is broken" -d MessageSid=SM123
```
Numbers ending in `0000` fail delivery with error `30007` so you can exercise the retry path. `STOP`, `START`
and `HELP` behave per TCPA. The React phone simulator (web plan) wraps this in a UI.

## API in one minute
`POST /api/auth/login` → cookie `sid`. Everything staff-facing lives under `/api/p/<propertyId>/…`:
`conversations`, `work-orders`, `quick-replies`, `assets`, `resolution-categories`, `users`, `departments`,
`notifications`, `analytics`, `guests`. WebSocket at `/ws` (send `{"type":"subscribe","propertyId":…}`).
Dev only: `/api/dev/sim/*`, `/api/dev/pms/*`. Models: `web/src/api/schema.json`.

## Moving to PostgreSQL
`pip install "psycopg[binary]"`, set `DATABASE_URL=postgresql+psycopg://…`, run `cd server && alembic upgrade head`.
Migrations use portable types; nothing else changes. Run one web process (`gunicorn -w 1 --threads 16`) because
presence and the realtime registry are in-memory.
```

- [ ] **Step 5: Full verification**

Run from `server/`:
```bash
python -m pytest -q
ruff check .
python -m seed.seed
START_WORKER=1 python run.py &
sleep 3
curl -s http://127.0.0.1:5000/api/health
curl -s -X POST http://127.0.0.1:5000/api/hooks/sms/inbound -H "X-Mock-Secret: dev" -d From=+15559876543 -d To=+15550100 -d "Body=Testing from curl" -d MessageSid=SM-curl-1 -o /dev/null -w "%{http_code}\n"
```
Expected: all tests pass; ruff reports no errors; health returns `{"status":"ok"}`; the webhook returns `204`. Log in as `ava@hvh.test` with curl (`-c cookies.txt`) and `GET /api/p/<HVH id>/conversations` to see the new conversation at the top. Stop the server.

- [ ] **Step 6: Commit**

```bash
cd ..
git add README.md package.json server
git commit -m "chore: dev entrypoint, root scripts, README with setup and seeded logins"
```

---

## Self-review notes (kept for the executor)

- **Spec coverage.** §4.1 domain table → Tasks 6, 7, 10–18. §4.2 channels → 9, 11. §4.3 PMS → 20. §4.4 queue → 8. §4.5 realtime → 7, 19. §4.6 auth → 4, 5. §4.7 API → 5, 7, 11, 12, 15, 16, 17, 18, 21. §4.8 type export → 23. §6 compliance → 6 (redaction), 10 (consent), 11 (send path/keywords), 4 (audit). §7 tests: criteria 1, 2, 5 → Task 11; 4 → 9 and 12; 6, 7 → 14; 8 → 13; 9 → 5; 10 → 12; 3 is the E2E in the web plan. §8 seed → 22. §9 config → 1, 24. §11 Postgres → 24 README.
- **Deliberate deviations from the spec text:** `app/clock.py` module instead of `app.clock` attribute (same purpose, thread-safe from the worker); the session table is `user_session`; `ChannelAdapter.send` takes `db` so the mock can enqueue delivery jobs; per-test DB copies instead of per-module (cheaper and simpler).
- **Names that must match across tasks:** `db_session`, `ok`, `parse_body`, `parse_query`, `no_content`, `client_meta` (Task 4); `queue_event`, `deliver`, `add_listener` (7); `jobs.enqueue`, `Worker.tick` (8); `messages.send/record_inbound/retry/update_delivery_status` (9, 11); `conversations.get/find_or_create_for_guest/list/detail/patch/guest_thread/touch_updated/assert_viewer_can_see` (11, 12); `work_orders.create/transition/assign/comment/set_priority/prefill_from_conversation/list/detail` (14, 15); `draft_prompts.create_for_completion/dismiss` (14, 15); `notifications.create/notify_user_or_department` (7); `users.list_departments/list_staff/members_of_department/create_staff/update_staff/remove_membership` (5, 17); fixture names `app, client, database, fx, login, events, worker, template_db_path` (3, 7, 8).
