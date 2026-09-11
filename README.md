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
npm run seed          # wipes and recreates server/data/app.db with realistic data
npm run server        # http://127.0.0.1:5200  (API + WebSocket + job worker)
npm run test:server   # pytest, including the §11.1 acceptance suite
```
Note: npm ≥ 11.19 blocks package install scripts by default; the server has no native dependencies, so this
does not affect the Python side. If a Node package needs its install script, run `npm install-scripts approve <pkg>`.

## Web client
Requires Node 20+.
```bash
cd web
npm install
npm run dev        # http://127.0.0.1:5173
```
Run the server in a second terminal (`.\start.bat` on Windows, or `npm run server` from the repo
root). Vite proxies `/api`, `/ws` and `/a/<short-code>` to `127.0.0.1:5200`, so there is no CORS to
configure in development. The dev server binds IPv4 explicitly, so reach it on `127.0.0.1`, not
`localhost`.

| Command (from `web/`) | What it does |
|---|---|
| `npm run dev` | Vite dev server on 5173 |
| `npm run build` | Type-check and build to `web/dist` |
| `npm test` | Vitest unit and component tests |
| `npm run test:e2e` | Playwright; starts both servers itself |
| `npm run gen:types` | Regenerate `src/api/types.generated.ts` from `src/api/schema.json` |

`npm run test:e2e` starts the API itself by running `python ../server/dev_start.py`, so activate the
venv first — the `python` it finds on PATH has to be the one the server is installed into. Once per
machine, install the browser it drives: `npx playwright install chromium`.

### Regenerating the API types
`web/src/api/schema.json` is written by the server, so after any change to a Pydantic
request/response model:
```bash
npm run schema      # from the repo root — writes web/src/api/schema.json
cd web && npm run gen:types
```
Both files are committed. `server/tests/test_schema_export.py` fails if the schema is stale, and a
Vitest fails if the generated types are.

### The phone simulator
`http://127.0.0.1:5173/sim` — dev builds only. Pick a seeded guest, text the hotel, and watch the
staff inbox react. Quick buttons cover `STOP`, `HELP`, a maintenance complaint and a card number
(to demonstrate redaction). Numbers ending `0000` fail delivery on purpose with mock error `30007`
so the retry path can be exercised.

### Themes
Dark is the default. The **Theme** control in the left nav toggles light, and the choice is saved
per user (`PATCH /api/auth/prefs`), so it follows them to another machine. With no saved choice the
device's `prefers-color-scheme` decides.

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

`ava@hvh.test` is a good default **for the inbox**: HVH holds all 30 seeded conversations, so it
lands on a populated one. She is an `agent`, though, so she cannot open Admin at all — the
nav item is hidden and the route 403s. Use **`alex@hvh.test`** for the admin screens, or
`morgan@hvh.test` for Analytics as a duty manager.
The same credentials sign in to the web client at `http://127.0.0.1:5173/login`.

## Texting the hotel without Twilio
The SMS wire is mocked (`SMS_ADAPTER=mock`). Send an inbound text exactly as Twilio would:
```bash
curl -X POST http://127.0.0.1:5200/api/hooks/sms/inbound -H "X-Mock-Secret: dev" \
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

## Configuration switches that matter
`server/.env.example` documents every variable; three of them are safety-relevant.
- **`ENABLE_DEV_ENDPOINTS`** — `/api/dev/*` is unauthenticated and lists every guest at every
  property (names, phone numbers, rooms, consent status). It registers only when this is
  explicitly `1`, and never when `FLASK_ENV=production`. `run.py` and `dev_start.py` set it for
  you locally; a deployment that sets nothing gets no dev routes.
- **`SESSION_COOKIE_SECURE`** — unset means the session cookie is `Secure` in production and not
  in development. Set it to `1`/`0` to force either way (HTTPS tunnel in dev, plain-HTTP staging).
- **`USE_RELOADER`** — set only by the dev entrypoints, which run Flask's auto-reloader. It tells
  `create_app` that a parent monitor process exists so the job worker starts in the reloader child
  only. Under gunicorn leave it unset and the worker starts whenever `START_WORKER=1`, regardless
  of `FLASK_ENV`.

In production (`FLASK_ENV=production`) the app refuses to start while `SESSION_SECRET` is still a
placeholder.

## Moving to PostgreSQL
`pip install "psycopg[binary]"`, set `DATABASE_URL=postgresql+psycopg://…`, run `cd server && alembic upgrade head`.
Migrations use portable types; nothing else changes. Run one web process (`gunicorn -w 1 --threads 16`) because
presence and the realtime registry are in-memory.
