"""Development entrypoint. Production: gunicorn -k gthread -w 1 --threads 16 'app:create_app()'"""
import os

from app import create_app
from app.config import Config

if __name__ == "__main__":
    os.environ.setdefault("START_WORKER", "1")
    os.environ.setdefault("ENABLE_DEV_ENDPOINTS", "1")
    os.environ.setdefault("USE_RELOADER", "1")
    cfg = Config.from_env()
    app = create_app(cfg)
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5200")), debug=cfg.USE_RELOADER,
            threaded=True)
