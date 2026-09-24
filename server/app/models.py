"""Database tables."""
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    TypeDecorator,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Stores UTC; always returns timezone-aware datetimes (SQLite drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc) if value is not None else None

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="viewer")  # admin | operator | viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class District(Base):
    """A part of the city (منطقه / ناحیه / محدوده طرح)."""

    __tablename__ = "districts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    code: Mapped[str] = mapped_column(String(32), default="")
    kind: Mapped[str] = mapped_column(String(32), default="district")  # district | traffic_zone | low_emission | other
    color: Mapped[str] = mapped_column(String(16), default="#3b82f6")
    polygon: Mapped[list] = mapped_column(JSON, default=list)  # [[lat, lng], ...]
    speed_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    cameras: Mapped[list["Camera"]] = relationship(back_populates="district")


class Camera(Base):
    __tablename__ = "cameras"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    vendor: Mapped[str] = mapped_column(String(32), default="rtsp")
    host: Mapped[str] = mapped_column(String(255), default="")
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    username: Mapped[str] = mapped_column(String(128), default="")
    password: Mapped[str] = mapped_column(String(256), default="")
    channel: Mapped[int] = mapped_column(Integer, default=1)
    stream: Mapped[str] = mapped_column(String(16), default="main")  # main | sub
    url: Mapped[str] = mapped_column(Text, default="")  # explicit URL overrides vendor template
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id", ondelete="SET NULL"), nullable=True)
    district: Mapped[District | None] = relationship(back_populates="cameras")
    address: Mapped[str] = mapped_column(String(255), default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    direction: Mapped[str] = mapped_column(String(64), default="")
    purpose: Mapped[str] = mapped_column(String(32), default="traffic")  # traffic | parking | entrance | mixed

    speed_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Analytics config: zones (polygons in normalized 0..1 coords), speed lines, flags
    zones: Mapped[list] = mapped_column(JSON, default=list)
    speed_calibration: Mapped[dict] = mapped_column(JSON, default=dict)
    analytics: Mapped[dict] = mapped_column(JSON, default=dict)

    # Runtime status (written by workers)
    status: Mapped[str] = mapped_column(String(16), default="offline")  # online | offline | error | disabled
    status_message: Mapped[str] = mapped_column(Text, default="")
    fps: Mapped[float] = mapped_column(Float, default=0.0)
    last_seen: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    lease_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Event(Base):
    """One vehicle observation (passage / parking) at a camera."""

    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True, index=True)
    district_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(24), default="passage")  # passage | parking | double_parking | stopped
    plate: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)  # raw e.g. 12Sin34567
    plate_fa: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plate_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    plate_category: Mapped[str | None] = mapped_column(String(24), nullable=True)
    plate_conf: Mapped[float | None] = mapped_column(Float, nullable=True)
    vehicle_type: Mapped[str] = mapped_column(String(24), default="unknown", index=True)
    is_heavy: Mapped[bool] = mapped_column(Boolean, default=False)
    is_pickup: Mapped[bool] = mapped_column(Boolean, default=False)
    loaded: Mapped[str] = mapped_column(String(12), default="unknown")  # loaded | empty | unknown
    color: Mapped[str] = mapped_column(String(16), default="unknown")
    speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    direction: Mapped[str] = mapped_column(String(16), default="")
    dwell_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    zone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vehicle_image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    plate_image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attrs: Mapped[dict] = mapped_column(JSON, default=dict)
    violations: Mapped[list["Violation"]] = relationship(back_populates="event")

    __table_args__ = (Index("ix_events_cam_ts", "camera_id", "ts"),)


class Violation(Base):
    __tablename__ = "violations"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=True, index=True)
    event: Mapped[Event | None] = relationship(back_populates="violations")
    camera_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    district_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    rule_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    plate: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(12), default="medium")  # low | medium | high | critical
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending | confirmed | rejected
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class AccessRule(Base):
    """Traffic access rule for a district (e.g. heavy vehicle ban, odd/even plan, permit area)."""

    __tablename__ = "access_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    kind: Mapped[str] = mapped_column(String(24), default="ban")  # ban | permit_required | odd_even
    district_ids: Mapped[list] = mapped_column(JSON, default=list)  # empty => whole city
    camera_ids: Mapped[list] = mapped_column(JSON, default=list)
    vehicle_types: Mapped[list] = mapped_column(JSON, default=list)  # empty => all vehicle types
    heavy_only: Mapped[bool] = mapped_column(Boolean, default=False)
    loaded: Mapped[str] = mapped_column(String(12), default="any")  # any | loaded | empty
    weekdays: Mapped[list] = mapped_column(JSON, default=list)  # 0=Sat .. 6=Fri; empty => every day
    time_windows: Mapped[list] = mapped_column(JSON, default=list)  # [{"start":"06:00","end":"20:00"}]
    exempt_categories: Mapped[list] = mapped_column(JSON, default=list)  # plate categories (taxi, government...)
    permit_types: Mapped[list] = mapped_column(JSON, default=list)  # permits that exempt
    even_weekdays: Mapped[list] = mapped_column(JSON, default=lambda: [0, 2, 4])  # odd_even: days even plates may enter
    severity: Mapped[str] = mapped_column(String(12), default="medium")
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Permit(Base):
    __tablename__ = "permits"
    id: Mapped[int] = mapped_column(primary_key=True)
    plate: Mapped[str] = mapped_column(String(32), index=True)
    permit_type: Mapped[str] = mapped_column(String(32), default="traffic_plan")
    district_ids: Mapped[list] = mapped_column(JSON, default=list)  # empty => all
    valid_from: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    owner: Mapped[str] = mapped_column(String(128), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Watchlist(Base):
    __tablename__ = "watchlist"
    id: Mapped[int] = mapped_column(primary_key=True)
    plate: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(String(32), default="wanted")  # stolen | wanted | suspicious | vip | other
    priority: Mapped[str] = mapped_column(String(12), default="high")
    note: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(24))  # watchlist | violation | camera
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    level: Mapped[str] = mapped_column(String(12), default="info")
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    camera_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(128), default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class WorkerNode(Base):
    __tablename__ = "workers"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    host: Mapped[str] = mapped_column(String(128), default="")
    device: Mapped[str] = mapped_column(String(32), default="cpu")
    capacity: Mapped[int] = mapped_column(Integer, default=0)
    cameras: Mapped[int] = mapped_column(Integer, default=0)
    cpu: Mapped[float] = mapped_column(Float, default=0.0)
    memory: Mapped[float] = mapped_column(Float, default=0.0)
    last_heartbeat: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
