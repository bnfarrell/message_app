#!/bin/sh
set -e

# Railway injects PORT; default only so the image runs locally.
: "${PORT:=8080}"

echo "==> alembic upgrade head"
alembic upgrade head

# -w 1 is a correctness requirement, not tuning. Presence, the WebSocket
# ConnectionRegistry and the background job worker all live in process memory,
# so a second worker would split presence and double-process the job queue.
# Keep the Railway replica count at 1 for the same reason.
echo "==> gunicorn on :$PORT"
exec gunicorn \
  --bind "0.0.0.0:$PORT" \
  --worker-class gthread \
  --workers 1 \
  --threads 16 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  "app:create_app()"
