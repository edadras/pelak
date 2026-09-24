from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.config import settings

TZ = ZoneInfo(settings.timezone)


def apply(obj, data: dict, fields):
    for f in fields:
        if f in data:
            setattr(obj, f, data[f])
    return obj


def row(obj, fields):
    out = {}
    for f in fields:
        v = getattr(obj, f)
        if isinstance(v, datetime):
            v = (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(TZ).isoformat()
        out[f] = v
    return out


def get_or_404(db, model, id_):
    obj = db.get(model, id_)
    if obj is None:
        raise HTTPException(404, "مورد یافت نشد")
    return obj


def parse_dt(value):
    """Accept ISO strings (local Tehran time when naive)."""
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(timezone.utc)
