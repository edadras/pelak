"""CRUD for districts, cameras, rules, permits, watchlist, users and settings."""
import base64
import csv
import io
import shutil
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.common import apply, get_or_404, parse_dt, row
from app.config import BASE_DIR
from app.core import plates
from app.core.bus import bus
from app.db import get_db
from app.models import AccessRule, Camera, District, Permit, Setting, User, Watchlist
from app.security import audit, current_user, hash_password, require
from app.vision.sources import build_url, mask_url

router = APIRouter(prefix="/api", tags=["admin"])

# ------------------------------------------------------------------ districts
DISTRICT_FIELDS = ["name", "code", "kind", "color", "polygon", "speed_limit", "description"]


@router.get("/districts")
def list_districts(db: Session = Depends(get_db), user=Depends(current_user)):
    out = []
    for d in db.query(District).order_by(District.id):
        item = row(d, ["id", *DISTRICT_FIELDS])
        item["camera_count"] = len(d.cameras)
        out.append(item)
    return out


@router.post("/districts")
async def create_district(request: Request, db: Session = Depends(get_db), user=Depends(require("admin"))):
    d = apply(District(), await request.json(), DISTRICT_FIELDS)
    if not d.name:
        raise HTTPException(400, "نام منطقه الزامی است")
    db.add(d)
    audit(db, user, "district.create", d.name)
    db.commit()
    return row(d, ["id", *DISTRICT_FIELDS])


@router.put("/districts/{id_}")
async def update_district(id_: int, request: Request, db: Session = Depends(get_db), user=Depends(require("admin"))):
    d = apply(get_or_404(db, District, id_), await request.json(), DISTRICT_FIELDS)
    audit(db, user, "district.update", d.name)
    db.commit()
    return row(d, ["id", *DISTRICT_FIELDS])


@router.delete("/districts/{id_}")
def delete_district(id_: int, db: Session = Depends(get_db), user=Depends(require("admin"))):
    d = get_or_404(db, District, id_)
    audit(db, user, "district.delete", d.name)
    db.delete(d)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ cameras
CAMERA_FIELDS = ["name", "vendor", "host", "port", "username", "password", "channel", "stream", "url", "enabled",
                 "district_id", "address", "lat", "lng", "direction", "purpose", "speed_limit", "zones",
                 "speed_calibration", "analytics"]
CAMERA_OUT = ["id", *[f for f in CAMERA_FIELDS if f != "password"], "status", "status_message", "fps",
              "last_seen", "worker_id", "config_version"]


def camera_out(c: Camera):
    item = row(c, CAMERA_OUT)
    item["has_password"] = bool(c.password)
    item["district_name"] = c.district.name if c.district else None
    try:
        item["stream_url"] = mask_url(build_url(_cam_cfg(c))) if c.vendor != "onvif" or c.url else "ONVIF (خودکار)"
    except Exception:
        item["stream_url"] = ""
    return item


def _cam_cfg(c: Camera):
    return {f: getattr(c, f) for f in ("vendor", "host", "port", "username", "password", "channel", "stream", "url")}


@router.get("/cameras")
def list_cameras(db: Session = Depends(get_db), user=Depends(current_user)):
    return [camera_out(c) for c in db.query(Camera).order_by(Camera.id)]


@router.get("/cameras/{id_}")
def get_camera(id_: int, db: Session = Depends(get_db), user=Depends(current_user)):
    return camera_out(get_or_404(db, Camera, id_))


def _clean_camera_payload(data):
    if data.get("password") in (None, "", "****"):
        data.pop("password", None)
    for k in ("port", "district_id", "speed_limit", "lat", "lng"):
        if k in data and data[k] in ("", None):
            data[k] = None
    return data


@router.post("/cameras")
async def create_camera(request: Request, db: Session = Depends(get_db), user=Depends(require("admin"))):
    data = _clean_camera_payload(await request.json())
    c = apply(Camera(), data, CAMERA_FIELDS)
    if not c.name:
        raise HTTPException(400, "نام دوربین الزامی است")
    c.status = "offline" if c.enabled else "disabled"
    db.add(c)
    audit(db, user, "camera.create", c.name)
    db.commit()
    return camera_out(c)


@router.put("/cameras/{id_}")
async def update_camera(id_: int, request: Request, db: Session = Depends(get_db), user=Depends(require("admin"))):
    c = get_or_404(db, Camera, id_)
    apply(c, _clean_camera_payload(await request.json()), CAMERA_FIELDS)
    c.config_version = (c.config_version or 0) + 1  # workers restart the camera with the new config
    if not c.enabled:
        c.status = "disabled"
    audit(db, user, "camera.update", c.name)
    db.commit()
    return camera_out(c)


@router.delete("/cameras/{id_}")
def delete_camera(id_: int, db: Session = Depends(get_db), user=Depends(require("admin"))):
    c = get_or_404(db, Camera, id_)
    audit(db, user, "camera.delete", c.name)
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.post("/cameras/test")
async def test_camera(request: Request, db: Session = Depends(get_db), user=Depends(require("operator"))):
    """Try to open a stream (saved camera or unsaved form data) and return one frame."""
    data = await request.json()
    cfg = dict(data)
    if data.get("id"):
        c = get_or_404(db, Camera, int(data["id"]))
        saved = _cam_cfg(c)
        cfg = {**saved, **{k: v for k, v in data.items() if v not in (None, "", "****")}}
    from app.vision.capture import grab_one
    from app.vision.engines import encode_jpeg

    try:
        url = await run_in_threadpool(build_url, cfg)
        frame = await run_in_threadpool(grab_one, url, 10)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    jpeg = encode_jpeg(frame, 80, 1280)
    h, w = frame.shape[:2]
    return {"ok": True, "url": mask_url(url), "width": w, "height": h,
            "image": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()}


@router.get("/cameras/{id_}/snapshot")
async def camera_snapshot(id_: int, cached: int = 0, raw: int = 0, db: Session = Depends(get_db),
                          user=Depends(current_user)):
    """Latest processed frame; falls back to grabbing directly from the camera (unless cached=1).

    raw=1 always grabs a clean frame from the camera (used by the zone editor).
    """
    from fastapi.responses import Response as R

    jpeg = None if raw else await bus.aget_frame(id_)
    if not jpeg and cached:
        raise HTTPException(404, "تصویر زنده در دسترس نیست")
    if not jpeg:
        c = get_or_404(db, Camera, id_)
        from app.vision.capture import grab_one
        from app.vision.engines import encode_jpeg

        try:
            frame = await run_in_threadpool(grab_one, build_url(_cam_cfg(c)), 10)
        except Exception as exc:
            raise HTTPException(503, f"تصویر دریافت نشد: {exc}") from None
        jpeg = encode_jpeg(frame, 80, 1280)
    return R(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/cameras/upload-video")
async def upload_video(file: UploadFile = File(...), user=Depends(require("admin"))):
    """Upload a recorded video to use as a test camera source (vendor = file)."""
    ext = (file.filename or "v.mp4").rsplit(".", 1)[-1].lower()
    if ext not in ("mp4", "avi", "mkv", "mov", "ts"):
        raise HTTPException(400, "فرمت ویدیو پشتیبانی نمی‌شود")
    target = BASE_DIR / "data" / "videos"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{uuid.uuid4().hex}.{ext}"
    with path.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    return {"path": str(path)}


# ------------------------------------------------------------------ rules
RULE_FIELDS = ["name", "enabled", "kind", "district_ids", "camera_ids", "vehicle_types", "heavy_only", "loaded",
               "weekdays", "time_windows", "exempt_categories", "permit_types", "even_weekdays", "severity",
               "description"]


@router.get("/rules")
def list_rules(db: Session = Depends(get_db), user=Depends(current_user)):
    return [row(r, ["id", *RULE_FIELDS]) for r in db.query(AccessRule).order_by(AccessRule.id)]


@router.post("/rules")
async def create_rule(request: Request, db: Session = Depends(get_db), user=Depends(require("admin"))):
    r = apply(AccessRule(), await request.json(), RULE_FIELDS)
    if not r.name:
        raise HTTPException(400, "نام قانون الزامی است")
    db.add(r)
    audit(db, user, "rule.create", r.name)
    db.commit()
    return row(r, ["id", *RULE_FIELDS])


@router.put("/rules/{id_}")
async def update_rule(id_: int, request: Request, db: Session = Depends(get_db), user=Depends(require("admin"))):
    r = apply(get_or_404(db, AccessRule, id_), await request.json(), RULE_FIELDS)
    audit(db, user, "rule.update", r.name)
    db.commit()
    return row(r, ["id", *RULE_FIELDS])


@router.delete("/rules/{id_}")
def delete_rule(id_: int, db: Session = Depends(get_db), user=Depends(require("admin"))):
    r = get_or_404(db, AccessRule, id_)
    audit(db, user, "rule.delete", r.name)
    db.delete(r)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ permits & watchlist
PERMIT_FIELDS = ["plate", "permit_type", "district_ids", "valid_from", "valid_to", "owner", "note"]
WATCH_FIELDS = ["plate", "reason", "priority", "note", "active"]


def _plate_in(value):
    raw = plates.normalize_query(value or "")
    if not plates.parse(raw):
        raise HTTPException(400, f"پلاک «{value}» معتبر نیست. نمونه: ۱۲ ب ۳۴۵ ۶۷")
    return raw


def _permit_out(p):
    item = row(p, ["id", *PERMIT_FIELDS, "created_at"])
    item["plate_fa"] = plates.format_fa(p.plate)
    return item


@router.get("/permits")
def list_permits(q: str = "", db: Session = Depends(get_db), user=Depends(current_user)):
    query = db.query(Permit)
    if q:
        query = query.filter(Permit.plate.like(f"%{plates.normalize_query(q)}%"))
    return [_permit_out(p) for p in query.order_by(Permit.id.desc()).limit(1000)]


@router.post("/permits")
async def create_permit(request: Request, db: Session = Depends(get_db), user=Depends(require("operator"))):
    data = await request.json()
    data["plate"] = _plate_in(data.get("plate"))
    data["valid_from"], data["valid_to"] = parse_dt(data.get("valid_from")), parse_dt(data.get("valid_to"))
    p = apply(Permit(), data, PERMIT_FIELDS)
    db.add(p)
    audit(db, user, "permit.create", p.plate)
    db.commit()
    return _permit_out(p)


@router.put("/permits/{id_}")
async def update_permit(id_: int, request: Request, db: Session = Depends(get_db), user=Depends(require("operator"))):
    data = await request.json()
    if "plate" in data:
        data["plate"] = _plate_in(data["plate"])
    for k in ("valid_from", "valid_to"):
        if k in data:
            data[k] = parse_dt(data[k])
    p = apply(get_or_404(db, Permit, id_), data, PERMIT_FIELDS)
    db.commit()
    return _permit_out(p)


@router.delete("/permits/{id_}")
def delete_permit(id_: int, db: Session = Depends(get_db), user=Depends(require("operator"))):
    db.delete(get_or_404(db, Permit, id_))
    db.commit()
    return {"ok": True}


@router.post("/permits/import")
async def import_permits(file: UploadFile = File(...), db: Session = Depends(get_db),
                         user=Depends(require("operator"))):
    """CSV columns: plate,permit_type,valid_from,valid_to,owner"""
    text = (await file.read()).decode("utf-8-sig")
    added, errors = 0, []
    for i, rec in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        try:
            db.add(Permit(plate=_plate_in(rec.get("plate")), permit_type=rec.get("permit_type") or "traffic_plan",
                          valid_from=parse_dt(rec.get("valid_from")), valid_to=parse_dt(rec.get("valid_to")),
                          owner=rec.get("owner") or ""))
            added += 1
        except Exception as exc:
            errors.append(f"سطر {i}: {getattr(exc, 'detail', exc)}")
    audit(db, user, "permit.import", str(added))
    db.commit()
    return {"added": added, "errors": errors[:50]}


def _watch_out(w):
    item = row(w, ["id", *WATCH_FIELDS, "created_at"])
    item["plate_fa"] = plates.format_fa(w.plate)
    return item


@router.get("/watchlist")
def list_watch(db: Session = Depends(get_db), user=Depends(current_user)):
    return [_watch_out(w) for w in db.query(Watchlist).order_by(Watchlist.id.desc())]


@router.post("/watchlist")
async def create_watch(request: Request, db: Session = Depends(get_db), user=Depends(require("operator"))):
    data = await request.json()
    data["plate"] = _plate_in(data.get("plate"))
    w = apply(Watchlist(), data, WATCH_FIELDS)
    db.add(w)
    audit(db, user, "watchlist.create", w.plate)
    db.commit()
    return _watch_out(w)


@router.put("/watchlist/{id_}")
async def update_watch(id_: int, request: Request, db: Session = Depends(get_db), user=Depends(require("operator"))):
    data = await request.json()
    if "plate" in data:
        data["plate"] = _plate_in(data["plate"])
    w = apply(get_or_404(db, Watchlist, id_), data, WATCH_FIELDS)
    db.commit()
    return _watch_out(w)


@router.delete("/watchlist/{id_}")
def delete_watch(id_: int, db: Session = Depends(get_db), user=Depends(require("operator"))):
    w = get_or_404(db, Watchlist, id_)
    audit(db, user, "watchlist.delete", w.plate)
    db.delete(w)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ users
@router.get("/users")
def list_users(db: Session = Depends(get_db), user=Depends(require("admin"))):
    return [row(u, ["id", "username", "full_name", "role", "is_active", "created_at", "last_login"])
            for u in db.query(User).order_by(User.id)]


@router.post("/users")
async def create_user(request: Request, db: Session = Depends(get_db), user=Depends(require("admin"))):
    data = await request.json()
    if not data.get("username") or len(data.get("password") or "") < 6:
        raise HTTPException(400, "نام کاربری و رمز (حداقل ۶ کاراکتر) الزامی است")
    if db.query(User).filter(User.username == data["username"]).first():
        raise HTTPException(400, "این نام کاربری وجود دارد")
    u = User(username=data["username"], full_name=data.get("full_name", ""), role=data.get("role", "viewer"),
             password_hash=hash_password(data["password"]))
    db.add(u)
    audit(db, user, "user.create", u.username)
    db.commit()
    return {"id": u.id}


@router.put("/users/{id_}")
async def update_user(id_: int, request: Request, db: Session = Depends(get_db), user=Depends(require("admin"))):
    data = await request.json()
    u = apply(get_or_404(db, User, id_), data, ["full_name", "role", "is_active"])
    if data.get("password"):
        if len(data["password"]) < 6:
            raise HTTPException(400, "رمز باید حداقل ۶ کاراکتر باشد")
        u.password_hash = hash_password(data["password"])
    audit(db, user, "user.update", u.username)
    db.commit()
    return {"ok": True}


@router.delete("/users/{id_}")
def delete_user(id_: int, db: Session = Depends(get_db), user=Depends(require("admin"))):
    u = get_or_404(db, User, id_)
    if u.id == user.id:
        raise HTTPException(400, "نمی‌توانید حساب خودتان را حذف کنید")
    db.delete(u)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ settings
DEFAULT_DETECTION = {"speed_tolerance": 5, "min_plate_conf": 0.0, "retention_days": 90}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), user=Depends(current_user)):
    s = db.get(Setting, "detection")
    return {**DEFAULT_DETECTION, **(s.value if s else {})}


@router.put("/settings")
async def put_settings(request: Request, db: Session = Depends(get_db), user=Depends(require("admin"))):
    data = await request.json()
    s = db.get(Setting, "detection") or Setting(key="detection", value={})
    s.value = {**DEFAULT_DETECTION, **(s.value or {}), **{k: data[k] for k in DEFAULT_DETECTION if k in data}}
    db.merge(s)
    audit(db, user, "settings.update")
    db.commit()
    return s.value
