# Concierge — hotel guest engagement & operations (Phase 1)

One codebase, one database: guests text the hotel; staff answer from a shared inbox; problems become work
orders; when the work order closes, the agent is prompted to tell the guest. Spec: `docs/design.md`.
Phase 1 scope and stack decisions: `docs/superpowers/specs/2026-09-10-hotel-engagement-phase1-design.md`.
Approved screens: `docs/mockups/` (Night Shift direction).

## Stack
Python 3.12+ · Flask 3 · SQLAlchemy 2 · Alembic · Pydantic v2 · flask-sock · pytest — SQLite now, PostgreSQL by
changing `DATABASE_URL`. Frontend: Vite + React + TypeScript (see the web plan).

## Fastest way to start (Windows)
Double-click `start.bat` at the repo root. It creates `server/data/`, runs migrations to head, seeds the
database only if it's empty, then starts the server with the job worker and SLA sweep running. It's safe to
double-click again — it will not re-seed over existing data. It requires the venv below to already exist; if
it doesn't, `start.bat` prints a message telling you to create it first.

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

`ava@hvh.test` is a good default: HVH holds all 30 seeded conversations, so it lands on a populated inbox.

## Texting the hotel without Twilio
The SMS wire is mocked (`SMS_ADAPTER=mock`). Send an inbound text exactly as Twilio would:
```bash
curl -X POST http://127.0.0.1:5000/api/hooks/sms/inbound -H "X-Mock-Secret: dev" \
  --data-urlencode From=+15551234567 --data-urlencode To=+15550100 \
  --data-urlencode "Body=The AC in 412 is broken" --data-urlencode MessageSid=SM123
```
(`--data-urlencode`, not plain `-d`, for the `+`-prefixed E.164 numbers: curl sends a bare `-d
From=+1555…` literally, and a raw `+` in an `application/x-www-form-urlencoded` body decodes
server-side to a space, so the leading `+` is silently lost and the phone number fails validation.)
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
