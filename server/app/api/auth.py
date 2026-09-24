from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.core import plates
from app.core.vehicles import COLORS, EVENT_KINDS, VEHICLE_TYPES, VIOLATION_TYPES, WEEKDAYS, ZONE_TYPES
from app.db import get_db
from app.models import User
from app.security import COOKIE, audit, create_token, current_user, hash_password, verify_password
from app.vision.sources import VENDORS

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login")
async def login(request: Request, response: Response, db: Session = Depends(get_db)):
    data = await request.json()
    user = db.query(User).filter(User.username == (data.get("username") or "").strip()).first()
    if not user or not user.is_active or not verify_password(data.get("password") or "", user.password_hash):
        raise HTTPException(401, "نام کاربری یا رمز عبور اشتباه است")
    user.last_login = datetime.now(timezone.utc)
    audit(db, user, "login")
    db.commit()
    token = create_token(user)
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", max_age=settings.token_hours * 3600)
    return {"token": token, "user": _user(user)}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return _user(user)


@router.post("/auth/password")
async def change_password(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = await request.json()
    if not verify_password(data.get("current") or "", user.password_hash):
        raise HTTPException(400, "رمز فعلی اشتباه است")
    if len(data.get("new") or "") < 6:
        raise HTTPException(400, "رمز جدید باید حداقل ۶ کاراکتر باشد")
    user.password_hash = hash_password(data["new"])
    audit(db, user, "change_password")
    db.commit()
    return {"ok": True}


def _user(u):
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role}


@router.get("/meta")
def meta(user: User = Depends(current_user)):
    lat, lng = (float(x) for x in settings.map_center.split(","))
    return {
        "app_name": settings.app_name,
        "vehicle_types": VEHICLE_TYPES,
        "colors": {k: {"label": v[0], "hex": v[1]} for k, v in COLORS.items()},
        "event_kinds": EVENT_KINDS,
        "violation_types": VIOLATION_TYPES,
        "zone_types": ZONE_TYPES,
        "weekdays": WEEKDAYS,
        "vendors": VENDORS,
        "plate_letters": plates.LETTERS,
        "plate_categories": plates.CATEGORY_LABELS,
        "map": {"tile_url": settings.map_tile_url, "center": [lat, lng]},
    }
