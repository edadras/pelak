import time

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app


def _client():
    c = TestClient(app)
    c.__enter__()  # run startup (init db + seed admin)
    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    c.headers["Authorization"] = "Bearer " + r.json()["token"]
    return c


def test_auth_required():
    with TestClient(app) as c:
        assert c.get("/api/cameras").status_code == 401
        assert c.post("/api/auth/login", json={"username": "admin", "password": "bad"}).status_code == 401


def test_full_flow_violation_and_watchlist_alert():
    c = _client()
    d = c.post("/api/districts", json={"name": "مرکز", "polygon": [[35.7, 51.4], [35.71, 51.4], [35.71, 51.41]]}).json()
    cam = c.post("/api/cameras", json={"name": "cam1", "vendor": "hikvision", "host": "10.0.0.5", "username": "admin",
                                       "password": "p@ss", "district_id": d["id"], "speed_limit": 50}).json()
    assert cam["stream_url"] == "rtsp://admin:****@10.0.0.5:554/Streaming/Channels/101"
    assert "password" not in cam
    c.post("/api/rules", json={"name": "ban trucks", "kind": "ban", "district_ids": [d["id"]], "vehicle_types": ["truck"]})
    assert c.post("/api/watchlist", json={"plate": "۱۲ ب ۳۴۵ ۶۷", "reason": "stolen"}).json()["plate"] == "12B34567"
    assert c.post("/api/watchlist", json={"plate": "nonsense"}).status_code == 400

    from app.worker.store import cache, store_observation

    cache._at = 0  # drop rule cache
    ok, jpg = cv2.imencode(".jpg", np.zeros((40, 60, 3), np.uint8))
    store_observation({
        "camera_id": cam["id"], "district_id": d["id"], "ts": time.time(), "kind": "passage",
        "plate": "12B34567", "plate_type": "national", "plate_conf": 0.9, "vehicle_type": "truck", "is_heavy": True,
        "loaded": "loaded", "color": "white", "speed_kmh": 80, "images": {"frame": jpg.tobytes()}, "attrs": {},
    })
    v = c.get("/api/violations").json()
    types = sorted(x["type"] for x in v["items"])
    assert types == ["heavy_vehicle", "speeding", "watchlist"], types
    assert c.get("/api/alerts?only_open=1").json()[0]["kind"] == "watchlist"

    ev = c.get("/api/events?plate=۱۲ ب").json()
    assert ev["total"] == 1 and ev["items"][0]["plate_fa"] == "۱۲ ب ۳۴۵ - ایران ۶۷"
    img = ev["items"][0]["image"]
    assert c.get("/media/" + img).status_code == 200
    assert c.get("/media/../../etc/passwd").status_code == 404

    prof = c.get("/api/vehicles/12B34567").json()
    assert prof["count"] == 1 and len(prof["violations"]) == 3

    vid = v["items"][0]["id"]
    assert c.put(f"/api/violations/{vid}", json={"status": "confirmed"}).json()["status"] == "confirmed"
    csv = c.get("/api/events/export")
    assert csv.status_code == 200 and "۱۲ ب ۳۴۵" in csv.text
    assert c.get("/api/stats/overview").json()["violations_today"] == 3
    assert c.get("/api/stats/breakdown?days=7").status_code == 200
    assert c.get("/api/stats/timeseries?days=7").status_code == 200


def test_viewer_cannot_modify():
    c = _client()
    c.post("/api/users", json={"username": "viewer1", "password": "secret1", "role": "viewer"})
    with TestClient(app) as v:
        tok = v.post("/api/auth/login", json={"username": "viewer1", "password": "secret1"}).json()["token"]
        v.headers["Authorization"] = "Bearer " + tok
        assert v.get("/api/cameras").status_code == 200
        assert v.post("/api/cameras", json={"name": "x"}).status_code == 403
