# Single service: build the React client, then serve it and the API from one Flask process.
#
# One origin is deliberate, not a convenience. Auth is a cookie and the inbox holds a
# WebSocket open; splitting the client onto a second domain would mean SameSite=None
# cookies and a CORS layer for no benefit. The client already fetches relative paths
# (web/src/api/client.ts), so same-origin needs no build-time API URL.

# ---------- stage 1: the client ----------
FROM node:22-alpine AS web

WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
# The golden-vector fixture lives at the repo root so neither language owns it. The web
# suite reads it with readFileSync at ../../../fixtures, so `tsc -b` does NOT need it and
# the build would succeed without this line — it is here so `npm test` works in this
# stage, which is the only way to run the drift check against the image's own sources.
COPY fixtures/ /src/fixtures/

RUN npm run build

# ---------- stage 2: the server ----------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_ENV=production

WORKDIR /app

COPY server/ /app/server/
RUN pip install /app/server

COPY --from=web /src/web/dist /app/web-dist
ENV WEB_DIST=/app/web-dist

COPY docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh

# alembic.ini sets `script_location = alembic`, resolved relative to the working
# directory, so migrations only run from here.
WORKDIR /app/server

EXPOSE 8080
CMD ["/app/docker-entrypoint.sh"]
