"""Runtime settings, read from environment variables (see .env.example)."""
import os
from pathlib import Path


def _env(name, default=None):
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def _bool(name, default=False):
    return str(_env(name, str(default))).lower() in {"1", "true", "yes", "on"}


BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent


class Settings:
    app_name = _env("APP_NAME", "سامانه هوشمند پایش تردد شهری")
    database_url = _env("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'pelak.db'}")
    redis_url = _env("REDIS_URL")  # empty => in-process bus (single node)
    secret_key = _env("SECRET_KEY", "change-me-in-production")
    token_hours = int(_env("TOKEN_HOURS", "12"))
    media_dir = Path(_env("MEDIA_DIR", str(BASE_DIR / "data" / "media")))
    timezone = _env("TZ_NAME", "Asia/Tehran")

    admin_username = _env("ADMIN_USERNAME", "admin")
    admin_password = _env("ADMIN_PASSWORD", "admin123")

    # Worker / vision
    embedded_worker = _bool("EMBEDDED_WORKER", False)
    worker_id = _env("WORKER_ID") or os.environ.get("HOSTNAME", "worker-local")
    worker_max_cameras = int(_env("WORKER_MAX_CAMERAS", "16"))
    lease_seconds = int(_env("LEASE_SECONDS", "30"))
    device = _env("DEVICE", "cpu")  # cpu | cuda | cuda:0
    process_fps = float(_env("PROCESS_FPS", "6"))
    vehicle_model = _env("VEHICLE_MODEL", "yolov8n.pt")
    vehicle_conf = float(_env("VEHICLE_CONF", "0.35"))
    attr_model = _env("ATTR_MODEL", str(REPO_DIR / "model" / "vehicle_attr.pt"))
    plate_repo_dir = Path(_env("PLATE_REPO_DIR", str(REPO_DIR)))
    plate_conf = float(_env("PLATE_CONF", "0.25"))
    char_conf = float(_env("CHAR_CONF", "0.25"))
    stream_fps = float(_env("STREAM_FPS", "5"))
    stream_width = int(_env("STREAM_WIDTH", "960"))

    map_tile_url = _env("MAP_TILE_URL", "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png")
    map_center = _env("MAP_CENTER", "35.6997,51.3380")  # Tehran
    retention_days = int(_env("RETENTION_DAYS", "90"))


settings = Settings()
settings.media_dir.mkdir(parents=True, exist_ok=True)
