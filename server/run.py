"""Development entrypoint. Production: gunicorn -k gthread -w 1 --threads 16 'app:create_app()'"""
import os

from app import create_app
from app.config import Config

if __name__ == "__main__":
    os.environ.setdefault("START_WORKER", "1")
    cfg = Config.from_env()
    app = create_app(cfg)
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=not cfg.is_production,
            threaded=True)
