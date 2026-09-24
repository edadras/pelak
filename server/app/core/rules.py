"""Traffic rules engine (pure logic, no database access).

``evaluate`` receives an observation (what the camera saw), the applicable rules and the
vehicle's permits, and returns a list of violation dicts.
"""
from dataclasses import dataclass, field
from datetime import time

from app.core import plates
from app.core.vehicles import HEAVY_TYPES, VEHICLE_TYPES, VIOLATION_TYPES, WEEKDAYS, weekday_sat0


@dataclass
class Observation:
    plate: str | None = None
    vehicle_type: str = "unknown"
    is_heavy: bool = False
    loaded: str = "unknown"
    speed_kmh: float | None = None
    kind: str = "passage"
    zone_type: str | None = None
    district_id: int | None = None
    camera_id: int | None = None
    extra: dict = field(default_factory=dict)


def _parse_hhmm(value):
    h, m = str(value).split(":")[:2]
    return time(int(h), int(m))


def in_windows(now, windows):
    """True if local time ``now`` falls in any window; empty list means all day."""
    if not windows:
        return True
    t = now.time()
    for w in windows:
        start, end = _parse_hhmm(w.get("start", "00:00")), _parse_hhmm(w.get("end", "23:59"))
        if start <= end:
            if start <= t <= end:
                return True
        elif t >= start or t <= end:  # crosses midnight
            return True
    return False


def rule_active(rule, now):
    if not rule.get("enabled", True):
        return False
    days = rule.get("weekdays") or []
    if days and weekday_sat0(now) not in days:
        return False
    return in_windows(now, rule.get("time_windows") or [])


def rule_applies_to_place(rule, district_id, camera_id):
    districts = rule.get("district_ids") or []
    cameras = rule.get("camera_ids") or []
    if cameras and camera_id in cameras:
        return True
    if districts:
        return district_id in districts
    return not cameras


def vehicle_matches(rule, obs):
    types = rule.get("vehicle_types") or []
    if types and obs.vehicle_type not in types:
        return False
    if rule.get("heavy_only") and not (obs.is_heavy or obs.vehicle_type in HEAVY_TYPES):
        return False
    loaded = rule.get("loaded", "any")
    if loaded == "loaded" and obs.loaded != "loaded":
        return False
    if loaded == "empty" and obs.loaded != "empty":
        return False
    return True


def permit_valid(permit, now, district_id, permit_types=None):
    if permit_types and permit.get("permit_type") not in permit_types:
        return False
    if permit.get("district_ids") and district_id not in permit["district_ids"]:
        return False
    vf, vt = permit.get("valid_from"), permit.get("valid_to")
    if vf and now < vf:
        return False
    if vt and now > vt:
        return False
    return True


def _window_text(rule):
    parts = []
    days = rule.get("weekdays") or []
    if days:
        parts.append("، ".join(WEEKDAYS[d] for d in sorted(days)))
    for w in rule.get("time_windows") or []:
        parts.append(f"{w.get('start')} تا {w.get('end')}")
    return " | ".join(parts) or "همه ساعات"


def _violation(vtype, rule, obs, title=None, **details):
    return {
        "type": vtype,
        "title": title or VIOLATION_TYPES.get(vtype, vtype),
        "rule_id": rule.get("id") if rule else None,
        "severity": (rule or {}).get("severity", "medium"),
        "plate": obs.plate,
        "details": details,
    }


def evaluate(obs, rules, permits, now, speed_limit=None, speed_tolerance=5):
    """Return violations for one observation.

    ``now`` must be timezone-aware local time (Asia/Tehran). ``permits`` are the permits of
    ``obs.plate`` as dicts with aware datetimes.
    """
    out = []
    category = plates.category(obs.plate) if obs.plate else "unknown"

    for rule in rules:
        if not rule_applies_to_place(rule, obs.district_id, obs.camera_id):
            continue
        if not rule_active(rule, now):
            continue
        if category in (rule.get("exempt_categories") or []):
            continue
        permit_types = rule.get("permit_types") or []
        has_permit = any(permit_valid(p, now, obs.district_id, permit_types or None) for p in permits)
        kind = rule.get("kind", "ban")
        when = _window_text(rule)

        if kind == "ban":
            if not vehicle_matches(rule, obs):
                continue
            if permit_types and has_permit:
                continue
            if rule.get("loaded") == "loaded":
                vtype = "loaded_vehicle"
            elif rule.get("heavy_only") or (
                rule.get("vehicle_types") and set(rule["vehicle_types"]) <= HEAVY_TYPES
            ):
                vtype = "heavy_vehicle"
            elif rule.get("time_windows") or rule.get("weekdays"):
                vtype = "restricted_time"
            else:
                vtype = "restricted_area"
            vname = VEHICLE_TYPES.get(obs.vehicle_type, obs.vehicle_type)
            out.append(_violation(vtype, rule, obs, f"{rule.get('name')}: تردد {vname} ممنوع ({when})",
                                  rule_name=rule.get("name"), when=when))

        elif kind == "permit_required":
            if not obs.plate or not vehicle_matches(rule, obs):
                continue
            if has_permit:
                continue
            out.append(_violation("no_permit", rule, obs, f"{rule.get('name')}: ورود بدون مجوز ({when})",
                                  rule_name=rule.get("name"), when=when))

        elif kind == "odd_even":
            if not obs.plate or not vehicle_matches(rule, obs):
                continue
            even = plates.is_even(obs.plate)
            if even is None or has_permit:
                continue
            even_day = weekday_sat0(now) in (rule.get("even_weekdays") or [0, 2, 4])
            if even != even_day:
                day = WEEKDAYS[weekday_sat0(now)]
                out.append(_violation("odd_even", rule, obs,
                                      f"{rule.get('name')}: پلاک {'زوج' if even else 'فرد'} در روز {day}",
                                      rule_name=rule.get("name"), plate_even=even, weekday=day))

    if speed_limit and obs.speed_kmh is not None and obs.speed_kmh > speed_limit + speed_tolerance:
        over = obs.speed_kmh - speed_limit
        sev = "critical" if over >= 40 else "high" if over >= 20 else "medium"
        out.append({
            "type": "speeding",
            "title": f"سرعت {round(obs.speed_kmh)} کیلومتر در ساعت (حد مجاز {speed_limit})",
            "rule_id": None,
            "severity": sev,
            "plate": obs.plate,
            "details": {"speed": round(obs.speed_kmh, 1), "limit": speed_limit},
        })

    parking_map = {
        "double_parking": ("double_parking", "high"),
        "no_parking": ("no_parking", "medium"),
        "stopped": ("stopped_in_lane", "medium"),
    }
    if obs.kind in parking_map:
        vtype, sev = parking_map[obs.kind]
        out.append({"type": vtype, "title": VIOLATION_TYPES[vtype], "rule_id": None, "severity": sev,
                    "plate": obs.plate, "details": {"zone": obs.zone_type, **obs.extra}})
    if obs.zone_type == "bus_lane" and obs.kind == "passage" and obs.vehicle_type not in ("bus", "minibus") \
            and category not in ("taxi", "police", "public"):
        out.append({"type": "bus_lane", "title": VIOLATION_TYPES["bus_lane"], "rule_id": None,
                    "severity": "medium", "plate": obs.plate, "details": {}})
    return out


def rule_to_dict(rule):
    return {c: getattr(rule, c) for c in (
        "id", "name", "enabled", "kind", "district_ids", "camera_ids", "vehicle_types", "heavy_only",
        "loaded", "weekdays", "time_windows", "exempt_categories", "permit_types", "even_weekdays", "severity",
    )}


def permit_to_dict(p):
    return {"permit_type": p.permit_type, "district_ids": p.district_ids or [],
            "valid_from": p.valid_from, "valid_to": p.valid_to}
