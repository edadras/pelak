"""Export vehicle crops recorded by the system, grouped by detected type, for labelling.

    python tools/export_crops.py --out crops --types pickup light_truck truck --limit 2000
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Event  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--types", nargs="*", default=[])
    ap.add_argument("--limit", type=int, default=1000)
    a = ap.parse_args()
    db = SessionLocal()
    q = db.query(Event).filter(Event.vehicle_image.isnot(None))
    if a.types:
        q = q.filter(Event.vehicle_type.in_(a.types))
    n = 0
    for e in q.order_by(Event.id.desc()).limit(a.limit):
        src = settings.media_dir / e.vehicle_image
        if src.exists():
            dst = Path(a.out) / e.vehicle_type / f"{e.id}.jpg"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
            n += 1
    print(f"exported {n} crops to {a.out}")
