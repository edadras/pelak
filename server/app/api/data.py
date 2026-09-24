"""Events, violations, alerts, statistics and vehicle history."""
import csv
import io
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.common import TZ, get_or_404, parse_dt
from app.core import plates
from app.core.jalali import format_dt
from app.core.vehicles import COLORS, VEHICLE_TYPES, VIOLATION_TYPES
from app.db import get_db
from app.models import Alert, Camera, District, Event, Violation, Watchlist
from app.security import audit, current_user, require
from app.worker.store import event_payload

router = APIRouter(prefix="/api", tags=["data"])
SEVERITY_LABELS = {"low": "کم", "medium": "متوسط", "high": "زیاد", "critical": "بحرانی"}
STATUS_LABELS = {"pending": "در انتظار بررسی", "confirmed": "تایید شده", "rejected": "رد شده"}


def _cams(db):
    return {c.id: c for c in db.query(Camera)}


def _event_filters(query, p, db):
    if p.get("plate"):
        pattern = plates.normalize_query(p["plate"])
        query = query.filter(Event.plate.like(f"%{pattern}%"))
    if p.get("camera_id"):
        query = query.filter(Event.camera_id == int(p["camera_id"]))
    if p.get("district_id"):
        query = query.filter(Event.district_id == int(p["district_id"]))
    for key in ("kind", "vehicle_type", "color", "loaded", "plate_category"):
        if p.get(key):
            query = query.filter(getattr(Event, key) == p[key])
    if p.get("heavy") == "1":
        query = query.filter(Event.is_heavy.is_(True))
    if p.get("has_plate") == "1":
        query = query.filter(Event.plate.isnot(None))
    if p.get("min_speed"):
        query = query.filter(Event.speed_kmh >= float(p["min_speed"]))
    if p.get("start"):
        query = query.filter(Event.ts >= parse_dt(p["start"]))
    if p.get("end"):
        query = query.filter(Event.ts <= parse_dt(p["end"]))
    return query


@router.get("/events")
def list_events(request: Request, db: Session = Depends(get_db), user=Depends(current_user)):
    p = dict(request.query_params)
    page, size = max(1, int(p.get("page", 1))), min(200, int(p.get("size", 50)))
    query = _event_filters(db.query(Event), p, db)
    total = query.count()
    cams = _cams(db)
    items = [event_payload(e, cams.get(e.camera_id))
             for e in query.order_by(Event.ts.desc()).offset((page - 1) * size).limit(size)]
    return {"total": total, "page": page, "size": size, "items": items}


@router.get("/events/export")
def export_events(request: Request, db: Session = Depends(get_db), user=Depends(require("operator"))):
    p = dict(request.query_params)
    query = _event_filters(db.query(Event), p, db).order_by(Event.ts.desc()).limit(100_000)
    cams = _cams(db)
    audit(db, user, "events.export")
    db.commit()

    def gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        buf.write("﻿")
        w.writerow(["شناسه", "تاریخ", "دوربین", "نوع رویداد", "پلاک", "نوع پلاک", "نوع خودرو", "سنگین",
                    "بار", "رنگ", "سرعت", "مدت توقف (ثانیه)"])
        for e in query:
            cam = cams.get(e.camera_id)
            w.writerow([e.id, format_dt(e.ts.astimezone(TZ)), cam.name if cam else "", e.kind, e.plate_fa or "",
                        plates.CATEGORY_LABELS.get(e.plate_category or "unknown"),
                        VEHICLE_TYPES.get(e.vehicle_type, e.vehicle_type), "بله" if e.is_heavy else "خیر",
                        {"loaded": "باردار", "empty": "بدون بار"}.get(e.loaded, "نامشخص"),
                        COLORS.get(e.color, COLORS["unknown"])[0], e.speed_kmh or "", e.dwell_seconds or ""])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()

    return StreamingResponse(gen(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=events.csv"})


@router.get("/events/{id_}")
def get_event(id_: int, db: Session = Depends(get_db), user=Depends(current_user)):
    e = get_or_404(db, Event, id_)
    out = event_payload(e, db.get(Camera, e.camera_id) if e.camera_id else None)
    out["violations"] = [_violation_out(v) for v in e.violations]
    return out


# ------------------------------------------------------------------ vehicle profile
@router.get("/vehicles/{plate}")
def vehicle_profile(plate: str, db: Session = Depends(get_db), user=Depends(current_user)):
    raw = plates.normalize_query(plate)
    events = db.query(Event).filter(Event.plate == raw).order_by(Event.ts.desc()).limit(300).all()
    cams = _cams(db)
    types = Counter(e.vehicle_type for e in events)
    colors = Counter(e.color for e in events if e.color != "unknown")
    return {
        "plate": plates.describe(raw),
        "events": [event_payload(e, cams.get(e.camera_id)) for e in events[:100]],
        "count": len(events),
        "first_seen": events[-1].ts.astimezone(TZ).isoformat() if events else None,
        "last_seen": events[0].ts.astimezone(TZ).isoformat() if events else None,
        "vehicle_type": types.most_common(1)[0][0] if types else None,
        "color": colors.most_common(1)[0][0] if colors else None,
        "violations": [_violation_out(v) for v in
                       db.query(Violation).filter(Violation.plate == raw).order_by(Violation.ts.desc()).limit(100)],
        "watchlist": [{"reason": w.reason, "note": w.note, "active": w.active}
                      for w in db.query(Watchlist).filter(Watchlist.plate == raw)],
        "path": [{"lat": cams[e.camera_id].lat, "lng": cams[e.camera_id].lng, "ts": e.ts.astimezone(TZ).isoformat(),
                  "camera": cams[e.camera_id].name}
                 for e in reversed(events[:100]) if e.camera_id in cams and cams[e.camera_id].lat],
    }


# ------------------------------------------------------------------ violations
def _violation_out(v: Violation, cams=None, event=None):
    ev = event or v.event
    cam = (cams or {}).get(v.camera_id)
    return {
        "id": v.id, "ts": v.ts.astimezone(TZ).isoformat(), "type": v.type,
        "type_label": VIOLATION_TYPES.get(v.type, v.type), "title": v.title, "plate": v.plate,
        "plate_fa": plates.format_fa(v.plate) if v.plate else None, "severity": v.severity,
        "severity_label": SEVERITY_LABELS.get(v.severity, v.severity), "status": v.status,
        "status_label": STATUS_LABELS.get(v.status, v.status), "camera_id": v.camera_id,
        "camera_name": cam.name if cam else None, "district_id": v.district_id, "event_id": v.event_id,
        "reviewed_by": v.reviewed_by, "note": v.note, "details": v.details or {},
        "image": ev.image if ev else None, "vehicle_image": ev.vehicle_image if ev else None,
        "plate_image": ev.plate_image if ev else None,
        "vehicle_type_label": VEHICLE_TYPES.get(ev.vehicle_type) if ev else None,
    }


def _violation_filters(query, p):
    if p.get("plate"):
        query = query.filter(Violation.plate.like(f"%{plates.normalize_query(p['plate'])}%"))
    for key in ("type", "status", "severity"):
        if p.get(key):
            query = query.filter(getattr(Violation, key) == p[key])
    for key in ("camera_id", "district_id"):
        if p.get(key):
            query = query.filter(getattr(Violation, key) == int(p[key]))
    if p.get("start"):
        query = query.filter(Violation.ts >= parse_dt(p["start"]))
    if p.get("end"):
        query = query.filter(Violation.ts <= parse_dt(p["end"]))
    return query


@router.get("/violations")
def list_violations(request: Request, db: Session = Depends(get_db), user=Depends(current_user)):
    p = dict(request.query_params)
    page, size = max(1, int(p.get("page", 1))), min(200, int(p.get("size", 50)))
    query = _violation_filters(db.query(Violation), p)
    total = query.count()
    cams = _cams(db)
    items = [_violation_out(v, cams) for v in
             query.order_by(Violation.ts.desc()).offset((page - 1) * size).limit(size)]
    return {"total": total, "page": page, "size": size, "items": items}


@router.get("/violations/export")
def export_violations(request: Request, db: Session = Depends(get_db), user=Depends(require("operator"))):
    query = _violation_filters(db.query(Violation), dict(request.query_params)).order_by(Violation.ts.desc())
    cams = _cams(db)
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf)
    w.writerow(["شناسه", "تاریخ", "نوع تخلف", "شرح", "پلاک", "دوربین", "شدت", "وضعیت"])
    for v in query.limit(100_000):
        cam = cams.get(v.camera_id)
        w.writerow([v.id, format_dt(v.ts.astimezone(TZ)), VIOLATION_TYPES.get(v.type, v.type), v.title,
                    plates.format_fa(v.plate) if v.plate else "", cam.name if cam else "",
                    SEVERITY_LABELS.get(v.severity), STATUS_LABELS.get(v.status)])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=violations.csv"})


@router.put("/violations/{id_}")
async def review_violation(id_: int, request: Request, db: Session = Depends(get_db),
                           user=Depends(require("operator"))):
    data = await request.json()
    v = get_or_404(db, Violation, id_)
    if data.get("status") in STATUS_LABELS:
        v.status = data["status"]
        v.reviewed_by, v.reviewed_at = user.username, datetime.now(timezone.utc)
    if "note" in data:
        v.note = data["note"]
    if data.get("plate"):
        raw = plates.normalize_query(data["plate"])
        if plates.parse(raw):
            v.plate = raw  # manual plate correction
    audit(db, user, "violation.review", str(v.id), status=v.status)
    db.commit()
    return _violation_out(v, _cams(db))


# ------------------------------------------------------------------ alerts
@router.get("/alerts")
def list_alerts(only_open: int = 0, db: Session = Depends(get_db), user=Depends(current_user)):
    q = db.query(Alert)
    if only_open:
        q = q.filter(Alert.acknowledged.is_(False))
    return [{"id": a.id, "ts": a.ts.astimezone(TZ).isoformat(), "kind": a.kind, "title": a.title, "body": a.body,
             "level": a.level, "event_id": a.event_id, "camera_id": a.camera_id, "acknowledged": a.acknowledged}
            for a in q.order_by(Alert.ts.desc()).limit(200)]


@router.post("/alerts/ack")
async def ack_alerts(request: Request, db: Session = Depends(get_db), user=Depends(require("operator"))):
    data = await request.json()
    q = db.query(Alert).filter(Alert.acknowledged.is_(False))
    if data.get("ids"):
        q = q.filter(Alert.id.in_(data["ids"]))
    n = q.update({Alert.acknowledged: True}, synchronize_session=False)
    db.commit()
    return {"acknowledged": n}


# ------------------------------------------------------------------ statistics
def _day_start(days_ago=0):
    now = datetime.now(TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
    return start.astimezone(timezone.utc)


@router.get("/stats/overview")
def overview(db: Session = Depends(get_db), user=Depends(current_user)):
    today = _day_start()
    cams = db.query(Camera).all()
    ev_today = db.query(func.count(Event.id)).filter(Event.ts >= today).scalar()
    ev_yesterday = db.query(func.count(Event.id)).filter(Event.ts >= _day_start(1), Event.ts < today).scalar()
    vio_today = db.query(func.count(Violation.id)).filter(Violation.ts >= today).scalar()
    pending = db.query(func.count(Violation.id)).filter(Violation.status == "pending").scalar()
    plates_today = db.query(func.count(func.distinct(Event.plate))).filter(Event.ts >= today,
                                                                           Event.plate.isnot(None)).scalar()
    heavy_today = db.query(func.count(Event.id)).filter(Event.ts >= today, Event.is_heavy.is_(True)).scalar()
    recent = datetime.now(timezone.utc) - timedelta(minutes=30)
    parked = db.query(func.count(Event.id)).filter(Event.ts >= recent, Event.kind == "parking").scalar()
    double = db.query(func.count(Event.id)).filter(Event.ts >= recent, Event.kind == "double_parking").scalar()
    alerts = db.query(func.count(Alert.id)).filter(Alert.acknowledged.is_(False)).scalar()
    avg_speed = db.query(func.avg(Event.speed_kmh)).filter(Event.ts >= today, Event.speed_kmh.isnot(None)).scalar()
    return {
        "events_today": ev_today, "events_yesterday": ev_yesterday, "violations_today": vio_today,
        "violations_pending": pending, "unique_plates_today": plates_today, "heavy_today": heavy_today,
        "parked_recent": parked, "double_parked_recent": double, "open_alerts": alerts,
        "avg_speed_today": round(avg_speed, 1) if avg_speed else None,
        "cameras_total": len(cams), "cameras_online": sum(1 for c in cams if c.status == "online"),
        "cameras_error": sum(1 for c in cams if c.status in ("error", "offline") and c.enabled),
    }


@router.get("/stats/timeseries")
def timeseries(days: int = 1, db: Session = Depends(get_db), user=Depends(current_user)):
    """Hourly buckets for 1 day, daily buckets otherwise (local time)."""
    start = _day_start(days - 1)
    fmt = "%H" if days == 1 else "%Y-%m-%d"
    ev = Counter()
    vio = Counter()
    for (ts,) in db.query(Event.ts).filter(Event.ts >= start):
        ev[ts.astimezone(TZ).strftime(fmt)] += 1
    for (ts,) in db.query(Violation.ts).filter(Violation.ts >= start):
        vio[ts.astimezone(TZ).strftime(fmt)] += 1
    if days == 1:
        keys = [f"{h:02d}" for h in range(24)]
        labels = [f"{h}:00" for h in range(24)]
    else:
        keys, labels = [], []
        for i in range(days):
            d = (start + timedelta(days=i)).astimezone(TZ)
            keys.append(d.strftime(fmt))
            labels.append(format_dt(d)[:10])
    return {"labels": labels, "events": [ev[k] for k in keys], "violations": [vio[k] for k in keys]}


@router.get("/stats/breakdown")
def breakdown(days: int = 1, db: Session = Depends(get_db), user=Depends(current_user)):
    start = _day_start(days - 1)
    base = db.query(Event).filter(Event.ts >= start)

    def group(col):
        return dict(db.query(col, func.count(Event.id)).filter(Event.ts >= start).group_by(col).all())

    vio = dict(db.query(Violation.type, func.count(Violation.id)).filter(Violation.ts >= start)
               .group_by(Violation.type).all())
    cams = {c.id: c.name for c in db.query(Camera)}
    dists = {d.id: d.name for d in db.query(District)}
    by_cam = group(Event.camera_id)
    by_dist = group(Event.district_id)
    speeds = [s for (s,) in base.with_entities(Event.speed_kmh).filter(Event.speed_kmh.isnot(None)).limit(20000)]
    bins = defaultdict(int)
    for s in speeds:
        bins[min(int(s // 10) * 10, 150)] += 1
    return {
        "vehicle_types": {VEHICLE_TYPES.get(k, k): v for k, v in group(Event.vehicle_type).items()},
        "colors": {k: {"label": COLORS.get(k, COLORS["unknown"])[0], "hex": COLORS.get(k, COLORS["unknown"])[1],
                       "count": v} for k, v in group(Event.color).items()},
        "kinds": group(Event.kind),
        "plate_categories": {plates.CATEGORY_LABELS.get(k or "unknown", "نامشخص"): v
                             for k, v in group(Event.plate_category).items()},
        "loaded": group(Event.loaded),
        "violations": {VIOLATION_TYPES.get(k, k): v for k, v in vio.items()},
        "cameras": sorted(({"name": cams.get(k, "حذف شده"), "count": v} for k, v in by_cam.items() if k),
                          key=lambda x: -x["count"])[:15],
        "districts": sorted(({"name": dists.get(k, "بدون منطقه"), "count": v} for k, v in by_dist.items()),
                            key=lambda x: -x["count"]),
        "speed_histogram": {f"{k}-{k + 9}": bins[k] for k in sorted(bins)},
    }


@router.get("/parking/current")
def parking_now(minutes: int = 30, db: Session = Depends(get_db), user=Depends(current_user)):
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    cams = _cams(db)
    evs = db.query(Event).filter(Event.ts >= since,
                                 Event.kind.in_(["parking", "double_parking", "no_parking", "stopped"])) \
        .order_by(Event.ts.desc()).limit(500).all()
    per_cam = defaultdict(lambda: Counter())
    for e in evs:
        per_cam[e.camera_id][e.kind] += 1
    return {
        "items": [event_payload(e, cams.get(e.camera_id)) for e in evs],
        "cameras": [{"camera_id": k, "camera_name": cams[k].name if k in cams else "", **v}
                    for k, v in per_cam.items()],
    }
