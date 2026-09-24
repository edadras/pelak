from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core import plates
from app.core.jalali import to_jalali
from app.core.rules import Observation, evaluate, in_windows
from app.vision.geometry import point_in_polygon, segments_cross

TZ = ZoneInfo("Asia/Tehran")
# 2026-09-26 is a Saturday (شنبه)
SAT = datetime(2026, 9, 26, 10, 0, tzinfo=TZ)
SUN = SAT + timedelta(days=1)


def test_plate_format_and_category():
    assert plates.format_fa("12Sin34567") == "۱۲ س ۳۴۵ - ایران ۶۷"
    assert plates.category("12Taxi34567") == "taxi"
    assert plates.category("12A34567") == "government"
    assert plates.category("12345") == "freezone"
    assert plates.parse("garbage") is None


def test_parity_uses_last_digit_of_three_digit_group():
    assert plates.is_even("12B34467") is True  # 344 -> 4
    assert plates.is_even("12B34567") is False  # 345 -> 5


def test_normalize_query():
    assert plates.normalize_query("۱۲ ب ۳۴۵ ایران ۶۷") == "12B34567"
    assert plates.normalize_query("۱۲الف۳۴۵۶۷") == "12A34567"
    assert plates.normalize_query("345") == "345"


def test_time_windows_cross_midnight():
    w = [{"start": "22:00", "end": "05:00"}]
    assert in_windows(SAT.replace(hour=23), w)
    assert in_windows(SAT.replace(hour=4), w)
    assert not in_windows(SAT.replace(hour=12), w)


def _ban(**kw):
    rule = {"id": 1, "name": "ban", "enabled": True, "kind": "ban", "district_ids": [1], "camera_ids": [],
            "vehicle_types": ["truck"], "heavy_only": False, "loaded": "any", "weekdays": [],
            "time_windows": [{"start": "06:00", "end": "20:00"}], "exempt_categories": [], "permit_types": [],
            "severity": "high"}
    rule.update(kw)
    return rule


def test_heavy_ban():
    obs = Observation(plate="12B34567", vehicle_type="truck", is_heavy=True, district_id=1)
    v = evaluate(obs, [_ban()], [], SAT)
    assert [x["type"] for x in v] == ["heavy_vehicle"]
    assert evaluate(obs, [_ban()], [], SAT.replace(hour=21)) == []  # outside hours
    assert evaluate(Observation(vehicle_type="car", district_id=1), [_ban()], [], SAT) == []
    assert evaluate(Observation(vehicle_type="truck", district_id=2), [_ban()], [], SAT) == []


def test_ban_permit_exempts():
    obs = Observation(plate="12B34567", vehicle_type="truck", district_id=1)
    rule = _ban(permit_types=["heavy"])
    permit = {"permit_type": "heavy", "district_ids": [], "valid_from": None, "valid_to": SAT + timedelta(days=1)}
    assert evaluate(obs, [rule], [permit], SAT) == []
    expired = dict(permit, valid_to=SAT - timedelta(days=1))
    assert len(evaluate(obs, [rule], [expired], SAT)) == 1


def test_loaded_pickup_rule():
    rule = _ban(vehicle_types=["pickup"], loaded="loaded")
    assert evaluate(Observation(vehicle_type="pickup", loaded="empty", district_id=1), [rule], [], SAT) == []
    v = evaluate(Observation(vehicle_type="pickup", loaded="loaded", district_id=1), [rule], [], SAT)
    assert v[0]["type"] == "loaded_vehicle"


def test_odd_even():
    rule = {"id": 2, "name": "زوج و فرد", "enabled": True, "kind": "odd_even", "district_ids": [1],
            "even_weekdays": [0, 2, 4], "time_windows": [], "weekdays": [0, 1, 2, 3, 4],
            "exempt_categories": ["taxi"], "permit_types": []}
    odd = Observation(plate="12B34567", vehicle_type="car", district_id=1)
    even = Observation(plate="12B34468", vehicle_type="car", district_id=1)
    assert [x["type"] for x in evaluate(odd, [rule], [], SAT)] == ["odd_even"]
    assert evaluate(even, [rule], [], SAT) == []
    assert evaluate(odd, [rule], [], SUN) == []
    assert len(evaluate(even, [rule], [], SUN)) == 1
    taxi = Observation(plate="12Taxi34567", vehicle_type="car", district_id=1)
    assert evaluate(taxi, [rule], [], SAT) == []


def test_permit_required():
    rule = {"id": 3, "name": "طرح", "enabled": True, "kind": "permit_required", "district_ids": [1],
            "time_windows": [{"start": "06:30", "end": "18:00"}], "permit_types": ["traffic_plan"]}
    obs = Observation(plate="12B34567", vehicle_type="car", district_id=1)
    assert evaluate(obs, [rule], [], SAT)[0]["type"] == "no_permit"
    permit = {"permit_type": "traffic_plan", "district_ids": [1], "valid_from": None, "valid_to": None}
    assert evaluate(obs, [rule], [permit], SAT) == []


def test_speed_and_parking():
    v = evaluate(Observation(speed_kmh=95), [], [], SAT, speed_limit=60)
    assert v[0]["type"] == "speeding" and v[0]["severity"] == "high"
    assert evaluate(Observation(speed_kmh=63), [], [], SAT, speed_limit=60) == []
    assert evaluate(Observation(kind="double_parking"), [], [], SAT)[0]["type"] == "double_parking"


def test_geometry():
    sq = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_polygon(5, 5, sq) and not point_in_polygon(15, 5, sq)
    assert segments_cross((5, -1), (5, 1), (0, 0), (10, 0))
    assert not segments_cross((5, 1), (5, 2), (0, 0), (10, 0))


def test_jalali():
    assert to_jalali(2026, 3, 21) == (1405, 1, 1)
    assert to_jalali(2024, 3, 20) == (1403, 1, 1)
