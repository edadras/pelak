from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

_url = settings.database_url
_kwargs = {"pool_pre_ping": True, "future": True}
if _url.startswith("sqlite"):
    Path(_url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    _kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
else:
    _kwargs.update(pool_size=10, max_overflow=20)

engine = create_engine(_url, **_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
IS_SQLITE = _url.startswith("sqlite")


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401 - register tables

    Base.metadata.create_all(engine)
