"""Serves the built React client from the same origin as the API.

Only active when WEB_DIST names a directory that exists, which is true in the production
image and false in development and under tests. So `GET /` stays a 404 by design
everywhere else, and no test sees a route it did not before.

One origin is deliberate: auth is a cookie and the inbox holds a WebSocket open, so
splitting the client onto a second domain would mean SameSite=None cookies and a CORS
layer for no benefit. The client already fetches relative paths (web/src/api/client.ts).
"""
from __future__ import annotations

import os

from flask import Flask, Response, send_from_directory
from werkzeug.exceptions import NotFound


def install(app: Flask) -> bool:
    """Register the SPA routes. Returns whether they were installed."""
    dist = os.getenv("WEB_DIST")
    if not dist or not os.path.isfile(os.path.join(dist, "index.html")):
        return False

    @app.get("/")
    def spa_index() -> Response:
        return _index(dist)

    @app.get("/<path:path>")
    def spa_asset(path: str) -> Response:
        # The API and the socket own their prefixes. An unknown path under them must stay
        # a 404 from the API — falling through to the shell would turn a mistyped endpoint
        # into a 200 full of HTML, which a client cannot distinguish from a real response.
        if path == "ws" or path.startswith("api/"):
            raise NotFound()

        # send_from_directory rejects traversal itself (werkzeug safe_join), so a "../"
        # path 404s rather than escaping dist.
        if os.path.isfile(os.path.join(dist, path)):
            response = send_from_directory(dist, path)
            if path.startswith("assets/"):
                # Vite fingerprints everything under assets/, so these are immutable.
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response

        # Client-side routes (/app/inbox, /login, …) are not files on disk.
        return _index(dist)

    return True


def _index(dist: str) -> Response:
    response = send_from_directory(dist, "index.html")
    # The shell names the fingerprinted bundles, so a cached copy would pin the browser
    # to a previous deploy's assets.
    response.headers["Cache-Control"] = "no-store"
    return response
