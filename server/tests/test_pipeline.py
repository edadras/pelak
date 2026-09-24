"""Behavioural tests for the camera pipeline using a scripted fake detector (no ML models)."""
import numpy as np

from app.vision.pipeline import CameraProcessor

W, H = 1000, 600


class FakeDetector:
    def __init__(self):
        self.script = lambda t: []
        self.t = 0.0

    def detect(self, frame, imgsz=640):
        return self.script(self.t)


class FakeEngines:
    def __init__(self):
        self.vehicle = FakeDetector()
        self.plate = None
        self.attr = None


def run(cam, script, seconds, fps=5):
    eng = FakeEngines()
    eng.vehicle.script = script
    out = []
    proc = CameraProcessor(cam, eng, out.append)
    frame = np.full((H, W, 3), 128, np.uint8)
    t = 0.0
    while t < seconds:
        eng.vehicle.t = t
        proc.process(frame, 1000 + t)
        t += 1 / fps
    proc.close()
    return out


CURB = {"name": "curb", "type": "curb_parking", "points": [[0, 0.5], [0.3, 0.5], [0.3, 1], [0, 1]]}
LANE = {"name": "lane", "type": "traffic_lane", "points": [[0.3, 0.5], [0.6, 0.5], [0.6, 1], [0.3, 1]]}


def test_double_parking_and_curb_parking():
    cam = {"id": 1, "zones": [CURB, LANE],
           "analytics": {"park_seconds": 10, "double_parking_seconds": 8, "detect_plates": False}}

    def script(t):
        dets = [((50, 350, 250, 500), "car", 0.9),     # parked at the curb
                ((320, 350, 520, 500), "car", 0.9)]    # stopped next to it in the lane
        # moving traffic passing by in the lane every few seconds
        x = int((t % 4) * 250)
        dets.append(((x, 100, x + 150, 200), "car", 0.9))
        return dets

    kinds = [o["kind"] for o in run(cam, script, 20)]
    assert "double_parking" in kinds
    assert "parking" in kinds


def test_stationary_in_lane_without_traffic_is_ignored():
    """A queue at a red light (nothing moving) must not be reported as double parking."""
    cam = {"id": 1, "zones": [CURB, LANE], "analytics": {"double_parking_seconds": 8}}
    kinds = [o["kind"] for o in run(cam, lambda t: [((320, 350, 520, 500), "car", 0.9)], 20)]
    assert "double_parking" not in kinds and "stopped" not in kinds


def test_speed_between_two_lines():
    # lines at y=0.3 and y=0.7 of the frame, 20 m apart; car moves 240 px/s downwards
    cam = {"id": 1, "zones": [], "analytics": {},
           "speed_calibration": {"line_a": [[0, 0.3], [1, 0.3]], "line_b": [[0, 0.7], [1, 0.7]], "distance_m": 20}}

    def script(t):
        y = int(t * 240)
        return [((400, y, 560, y + 100), "car", 0.9)] if y < H else []

    out = run(cam, script, 4, fps=10)
    passage = [o for o in out if o["kind"] == "passage"]
    assert passage and passage[0]["speed_kmh"] is not None
    # 240 px (0.4 * 600) per 20 m -> 20 m in 1 s -> 72 km/h
    assert abs(passage[0]["speed_kmh"] - 72) < 8
    assert passage[0]["direction"] == "a_to_b"
