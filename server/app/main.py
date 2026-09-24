import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, auth, data, live
from app.config import BASE_DIR, settings
from app.core.seed import seed
from app.db import init_db, session_scope
from app.models import Event, Setting

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(_app):
    init_db()
    seed()
    task = asyncio.create_task(retention_loop())
    if settings.embedded_worker:
        from app.worker.main import start_background_worker

        start_background_worker()
        log.info("embedded vision worker started")
    yield
    task.cancel()


app = FastAPI(title=settings.app_name, version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json",
              lifespan=lifespan)
for r in (auth.router, admin.router, data.router, live.router):
    app.include_router(r)

STATIC = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True}


@app.exception_handler(ValueError)
async def value_error(request: Request, exc: ValueError):
    return JSONResponse({"detail": f"مقدار نامعتبر: {exc}"}, status_code=400)


async def retention_loop():
    """Delete events (and their images) older than the configured retention period."""
    while True:
        try:
            await asyncio.to_thread(cleanup_old_events)
        except Exception:
            log.exception("retention cleanup failed")
        await asyncio.sleep(6 * 3600)


def cleanup_old_events():
    with session_scope() as db:
        s = db.get(Setting, "detection")
        days = int((s.value if s else {}).get("retention_days") or settings.retention_days)
        if days <= 0:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        old = db.query(Event).filter(Event.ts < cutoff).limit(20000).all()
        for e in old:
            for rel in (e.image, e.vehicle_image, e.plate_image):
                if rel:
                    try:
                        (settings.media_dir / rel).unlink(missing_ok=True)
                    except OSError:
                        pass
            db.delete(e)
        if old:
            log.info("retention: removed %s events older than %s days", len(old), days)
