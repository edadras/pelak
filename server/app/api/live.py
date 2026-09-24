"""Live streams, WebSocket event feed, media files and system status."""
import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.bus import bus
from app.db import get_db
from app.models import Camera, WorkerNode
from app.security import COOKIE, current_user

router = APIRouter(tags=["live"])


@router.get("/api/cameras/{id_}/stream.mjpg")
async def mjpeg(id_: int, user=Depends(current_user)):
    boundary = "frame"

    async def gen():
        last = None
        idle = 0
        while True:
            jpeg = await bus.aget_frame(id_)
            if jpeg and jpeg is not last:
                last = jpeg
                idle = 0
                yield (f"--{boundary}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n"
                       ).encode() + jpeg + b"\r\n"
            else:
                idle += 1
                if idle > 600:  # 2 minutes without frames
                    break
            await asyncio.sleep(1.0 / max(settings.stream_fps, 1))

    return StreamingResponse(gen(), media_type=f"multipart/x-mixed-replace; boundary={boundary}",
                             headers={"Cache-Control": "no-store"})


@router.get("/media/{path:path}")
def media(path: str, user=Depends(current_user)):
    root = settings.media_dir.resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        raise HTTPException(404, "فایل یافت نشد")
    return FileResponse(target, headers={"Cache-Control": "private, max-age=86400"})


@router.websocket("/ws")
async def ws(websocket: WebSocket):
    import jwt

    token = websocket.cookies.get(COOKIE) or websocket.query_params.get("token")
    try:
        jwt.decode(token or "", settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    try:
        async for message in bus.subscribe():
            await websocket.send_text(message)
    except (WebSocketDisconnect, RuntimeError):
        pass


@router.get("/api/system")
def system(db: Session = Depends(get_db), user=Depends(current_user)):
    now = datetime.now(timezone.utc)
    workers = []
    for w in db.query(WorkerNode):
        hb = w.last_heartbeat if w.last_heartbeat.tzinfo else w.last_heartbeat.replace(tzinfo=timezone.utc)
        workers.append({"id": w.id, "host": w.host, "device": w.device, "capacity": w.capacity,
                        "cameras": w.cameras, "cpu": w.cpu, "memory": w.memory,
                        "alive": now - hb < timedelta(seconds=settings.lease_seconds * 2),
                        "last_heartbeat": hb.isoformat()})
    disk = None
    try:
        import shutil

        total, used, free = shutil.disk_usage(settings.media_dir)
        disk = {"total_gb": round(total / 1e9, 1), "free_gb": round(free / 1e9, 1),
                "used_percent": round(used / total * 100, 1)}
    except Exception:
        pass
    cams = db.query(Camera).all()
    return {
        "workers": workers,
        "disk": disk,
        "bus": "redis" if settings.redis_url else "memory",
        "database": settings.database_url.split(":")[0],
        "cameras": {"total": len(cams), "enabled": sum(c.enabled for c in cams),
                    "unassigned": sum(1 for c in cams if c.enabled and not c.worker_id)},
        "capacity": sum(w["capacity"] for w in workers if w["alive"]),
    }
