"""Persist observations: images, events, rule evaluation, violations and watchlist alerts."""
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.config import settings
from app.core import plates as plate_utils
from app.core.bus import bus
from app.core.rules import Observation, evaluate, permit_to_dict, rule_to_dict
from app.core.vehicles import COLORS, EVENT_KINDS, VEHICLE_TYPES
from app.db import session_scope
from app.models import AccessRule, Alert, Camera, District, Event, Permit, Setting, Violation, Watchlist

log = logging.getLogger(__name__)
TZ = ZoneInfo(settings.timezone)


def save_image(data: bytes | None, ts: datetime, suffix: str):
    if not data:
        return None
    rel = f"{ts:%Y/%m/%d}/{uuid.uuid4().hex}_{suffix}.jpg"
    path = settings.media_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel


class RuleCache:
    def __init__(self, ttl=15):
        self.ttl = ttl
        self._at = 0
        self._lock = threading.Lock()
        self.rules, self.watch, self.speed_limits, self.options = [], {}, {}, {}

    def get(self, db):
        with self._lock:
            if time.time() - self._at > self.ttl:
                self.rules = [rule_to_dict(r) for r in db.query(AccessRule).filter(AccessRule.enabled.is_(True))]
                self.watch = {w.plate: {"reason": w.reason, "priority": w.priority, "note": w.note}
                              for w in db.query(Watchlist).filter(Watchlist.active.is_(True))}
                self.speed_limits = {d.id: d.speed_limit for d in db.query(District) if d.speed_limit}
                opt = db.get(Setting, "detection")
                self.options = opt.value if opt else {}
                self._at = time.time()
            return self


cache = RuleCache()


def store_observation(obs: dict):
    ts = datetime.fromtimestamp(obs["ts"], timezone.utc)
    imgs = obs.get("images") or {}
    with session_scope() as db:
        c = cache.get(db)
        cam = db.get(Camera, obs["camera_id"]) if obs.get("camera_id") else None
        min_conf = float(c.options.get("min_plate_conf", 0.0) or 0)
        plate = obs.get("plate")
        if plate and obs.get("plate_conf") is not None and obs["plate_conf"] < min_conf:
            plate = None
        ev = Event(
            ts=ts, camera_id=obs.get("camera_id"), district_id=obs.get("district_id"), kind=obs["kind"],
            plate=plate, plate_fa=plate_utils.format_fa(plate) if plate else None,
            plate_type=obs.get("plate_type") if plate else None,
            plate_category=plate_utils.category(plate) if plate else None,
            plate_conf=obs.get("plate_conf") if plate else None,
            vehicle_type=obs.get("vehicle_type", "unknown"), is_heavy=bool(obs.get("is_heavy")),
            is_pickup=bool(obs.get("is_pickup")), loaded=obs.get("loaded", "unknown"),
            color=obs.get("color", "unknown"), speed_kmh=obs.get("speed_kmh"), direction=obs.get("direction", ""),
            dwell_seconds=obs.get("dwell_seconds"), zone=obs.get("zone"), confidence=obs.get("confidence", 0),
            image=save_image(imgs.get("frame"), ts, "f"), vehicle_image=save_image(imgs.get("vehicle"), ts, "v"),
            plate_image=save_image(imgs.get("plate"), ts, "p"), attrs=obs.get("attrs") or {},
        )
        db.add(ev)
        db.flush()

        permits = []
        if plate:
            permits = [permit_to_dict(p) for p in db.query(Permit).filter(Permit.plate == plate)]
        speed_limit = (cam.speed_limit if cam else None) or c.speed_limits.get(obs.get("district_id"))
        local_now = ts.astimezone(TZ)
        observation = Observation(
            plate=plate, vehicle_type=ev.vehicle_type, is_heavy=ev.is_heavy, loaded=ev.loaded,
            speed_kmh=ev.speed_kmh, kind=ev.kind, zone_type=obs.get("zone_type"),
            district_id=ev.district_id, camera_id=ev.camera_id,
            extra={"dwell": ev.dwell_seconds} if ev.dwell_seconds else {},
        )
        found = evaluate(observation, c.rules, permits, local_now, speed_limit,
                         float(c.options.get("speed_tolerance", 5)))
        violations = []
        for v in found:
            vio = Violation(ts=ts, event_id=ev.id, camera_id=ev.camera_id, district_id=ev.district_id,
                            rule_id=v["rule_id"], type=v["type"], title=v["title"], plate=plate,
                            severity=v["severity"], details=v["details"])
            db.add(vio)
            violations.append(vio)

        alerts = []
        if plate and plate in c.watch:
            w = c.watch[plate]
            where = cam.name if cam else "نامشخص"
            alerts.append(Alert(ts=ts, kind="watchlist", level="critical",
                                title=f"خودرو تحت پیگیری: {plate_utils.format_fa(plate)}",
                                body=f"دیده شده در دوربین «{where}» — {w['note'] or w['reason']}",
                                event_id=ev.id, camera_id=ev.camera_id))
            db.add(Violation(ts=ts, event_id=ev.id, camera_id=ev.camera_id, district_id=ev.district_id,
                             type="watchlist", title="خودرو تحت تعقیب", plate=plate, severity="critical",
                             details=w))
        for a in alerts:
            db.add(a)
        db.flush()

        payload = event_payload(ev, cam)
        payload["violations"] = [{"id": v.id, "type": v.type, "title": v.title, "severity": v.severity}
                                 for v in violations]
    bus.publish({"type": "event", "data": payload})
    for a in alerts:
        bus.publish({"type": "alert", "data": {"id": a.id, "title": a.title, "body": a.body, "level": a.level,
                                               "event_id": a.event_id}})
    return payload


def event_payload(ev: Event, cam: Camera | None = None):
    local = ev.ts.astimezone(TZ) if ev.ts.tzinfo else ev.ts.replace(tzinfo=timezone.utc).astimezone(TZ)
    return {
        "id": ev.id,
        "ts": local.isoformat(),
        "camera_id": ev.camera_id,
        "camera_name": cam.name if cam else None,
        "district_id": ev.district_id,
        "kind": ev.kind,
        "kind_label": EVENT_KINDS.get(ev.kind, ev.kind),
        "plate": ev.plate,
        "plate_fa": ev.plate_fa,
        "plate_category": ev.plate_category,
        "plate_category_label": plate_utils.CATEGORY_LABELS.get(ev.plate_category or "unknown", "نامشخص"),
        "plate_conf": ev.plate_conf,
        "vehicle_type": ev.vehicle_type,
        "vehicle_type_label": VEHICLE_TYPES.get(ev.vehicle_type, ev.vehicle_type),
        "is_heavy": ev.is_heavy,
        "is_pickup": ev.is_pickup,
        "loaded": ev.loaded,
        "color": ev.color,
        "color_label": COLORS.get(ev.color, COLORS["unknown"])[0],
        "color_hex": COLORS.get(ev.color, COLORS["unknown"])[1],
        "speed_kmh": ev.speed_kmh,
        "direction": ev.direction,
        "dwell_seconds": ev.dwell_seconds,
        "zone": ev.zone,
        "confidence": ev.confidence,
        "image": ev.image,
        "vehicle_image": ev.vehicle_image,
        "plate_image": ev.plate_image,
        "attrs": ev.attrs or {},
    }
