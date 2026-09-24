import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import AuditLog, User

ROLES = {"viewer": 0, "operator": 1, "admin": 2}
COOKIE = "pelak_token"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return f"pbkdf2${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 240_000)
    return hmac.compare_digest(check.hex(), digest)


def create_token(user: User) -> str:
    payload = {
        "sub": user.username,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.token_hours),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def _token_from_request(request: Request):
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]
    return request.cookies.get(COOKIE) or request.query_params.get("token")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _token_from_request(request)
    if not token:
        raise HTTPException(401, "ابتدا وارد سامانه شوید")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "نشست شما منقضی شده است") from None
    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if not user or not user.is_active:
        raise HTTPException(401, "کاربر غیرفعال است")
    return user


def require(role: str):
    def dep(user: User = Depends(current_user)) -> User:
        if ROLES.get(user.role, 0) < ROLES[role]:
            raise HTTPException(403, "دسترسی کافی ندارید")
        return user

    return dep


def audit(db: Session, user: User | None, action: str, target: str = "", **details):
    db.add(AuditLog(username=user.username if user else "", action=action, target=target, details=details))
