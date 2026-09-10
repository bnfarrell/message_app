from app import create_app
from app.config import Config

if __name__ == "__main__":
    cfg = Config.from_env()
    app = create_app(cfg)
    app.run(host="127.0.0.1", port=5000, debug=not cfg.is_production, threaded=True)
