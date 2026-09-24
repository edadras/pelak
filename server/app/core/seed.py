"""First-run data: admin user, default settings and example districts/rules."""
import logging
import os

from app.config import REPO_DIR, settings
from app.db import session_scope
from app.models import AccessRule, Camera, District, Setting, User
from app.security import hash_password

log = logging.getLogger(__name__)

# Rough example polygons around central Tehran (edit on the map page).
EXAMPLE_DISTRICTS = [
    {"name": "محدوده طرح ترافیک", "code": "TP", "kind": "traffic_zone", "color": "#ef4444", "speed_limit": 50,
     "polygon": [[35.7155, 51.3790], [35.7160, 51.4350], [35.6690, 51.4360], [35.6680, 51.3800]]},
    {"name": "محدوده کنترل آلودگی هوا", "code": "LEZ", "kind": "low_emission", "color": "#f59e0b",
     "speed_limit": 50,
     "polygon": [[35.7400, 51.3500], [35.7420, 51.4650], [35.6500, 51.4680], [35.6480, 51.3520]]},
    {"name": "منطقه ۶", "code": "R6", "kind": "district", "color": "#3b82f6", "speed_limit": 60,
     "polygon": [[35.7450, 51.3700], [35.7450, 51.4100], [35.7150, 51.4100], [35.7150, 51.3700]]},
]


def seed():
    with session_scope() as db:
        if not db.query(User).first():
            db.add(User(username=settings.admin_username, full_name="مدیر سامانه", role="admin",
                        password_hash=hash_password(settings.admin_password)))
            log.warning("created admin user '%s' — change the password after first login", settings.admin_username)
        if not db.get(Setting, "detection"):
            db.add(Setting(key="detection", value={"speed_tolerance": 5, "min_plate_conf": 0.0,
                                                   "retention_days": settings.retention_days}))
        if os.environ.get("SEED_EXAMPLES", "1") == "1" and not db.query(District).first():
            districts = [District(**d) for d in EXAMPLE_DISTRICTS]
            db.add_all(districts)
            db.flush()
            tp, lez = districts[0].id, districts[1].id
            db.add_all([
                AccessRule(name="ممنوعیت تردد کامیون و تریلی در محدوده طرح", kind="ban", district_ids=[tp],
                           vehicle_types=["truck", "trailer", "light_truck"], heavy_only=False,
                           weekdays=[0, 1, 2, 3, 4, 5], time_windows=[{"start": "06:00", "end": "21:00"}],
                           severity="high", description="نمونه — در صفحه قوانین قابل ویرایش است"),
                AccessRule(name="طرح ترافیک (نیازمند مجوز)", kind="permit_required", district_ids=[tp],
                           weekdays=[0, 1, 2, 3, 4], time_windows=[{"start": "06:30", "end": "18:00"}],
                           exempt_categories=["taxi", "public", "police", "government", "disabled"],
                           permit_types=["traffic_plan"], severity="medium", enabled=False),
                AccessRule(name="طرح زوج و فرد", kind="odd_even", district_ids=[lez],
                           weekdays=[0, 1, 2, 3, 4], time_windows=[{"start": "06:30", "end": "19:00"}],
                           even_weekdays=[0, 2, 4], exempt_categories=["taxi", "public", "police", "disabled"],
                           permit_types=["traffic_plan", "odd_even"], severity="low", enabled=False),
                AccessRule(name="ممنوعیت تردد وانت باردار در ساعات اوج", kind="ban", district_ids=[lez],
                           vehicle_types=["pickup"], loaded="loaded",
                           time_windows=[{"start": "07:00", "end": "10:00"}, {"start": "16:00", "end": "20:00"}],
                           severity="medium", enabled=False),
            ])
        demo = os.environ.get("DEMO_VIDEO")
        if demo and not db.query(Camera).first():
            path = demo if os.path.isabs(demo) else str(REPO_DIR / demo)
            if os.path.exists(path):
                db.add(Camera(name="دوربین نمایشی (ویدیو)", vendor="file", url=path, lat=35.6997, lng=51.3380,
                              address="ویدیوی آزمایشی", analytics={"plate_mode": "vehicle"}))
