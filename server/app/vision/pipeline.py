"""Per-camera analytics: tracking, plates, attributes, speed and parking behaviour.

``CameraProcessor.process(frame, ts)`` is called for each sampled frame and returns an
annotated preview frame. Finished observations are handed to ``sink(observation)``.
"""
import logging
import time
from collections import Counter

import cv2
import numpy as np

from app.core import plates as plate_utils
from app.core.vehicles import CARGO_TYPES, HEAVY_TYPES
from app.vision.attributes import SizeReference, classify_color, estimate_loaded, refine_type
from app.vision.engines import crop, encode_jpeg
from app.vision.geometry import point_in_polygon, segments_cross
from app.vision.tracker import Tracker

log = logging.getLogger(__name__)

DEFAULTS = {
    "detect_plates": True,
    "plate_mode": "vehicle",  # vehicle: read plates on vehicle crops | frame: full frame (close-up ANPR)
    "imgsz": 640,
    "min_hits": 3,
    "park_seconds": 60,
    "no_parking_seconds": 30,
    "double_parking_seconds": 45,
    "stationary_window": 4.0,
    "plate_max_attempts": 14,
    "min_plate_width": 50,
}

ZONE_COLORS = {
    "curb_parking": (80, 200, 80), "no_parking": (60, 60, 230), "traffic_lane": (0, 190, 250),
    "bus_lane": (220, 120, 40), "detection": (200, 200, 200),
}
TYPE_COLORS = {"car": (255, 200, 60), "pickup": (60, 220, 255), "truck": (40, 120, 255),
               "trailer": (40, 60, 255), "light_truck": (40, 160, 255), "bus": (200, 90, 255),
               "minibus": (200, 120, 255), "motorcycle": (120, 255, 120)}


class CameraProcessor:
    def __init__(self, camera: dict, engines, sink):
        self.cam = camera
        self.engines = engines
        self.sink = sink
        self.cfg = {**DEFAULTS, **(camera.get("analytics") or {})}
        self.tracker = Tracker()
        self.size_ref = SizeReference()
        self.frame_no = 0
        self.zones = [z for z in (camera.get("zones") or []) if len(z.get("points") or []) >= 3]
        self.calib = camera.get("speed_calibration") or {}
        self._homography = None
        self._shape = None
        self.stats = Counter()

    # ------------------------------------------------------------------ helpers
    def _px(self, pts, shape):
        h, w = shape[:2]
        return [(float(x) * w, float(y) * h) for x, y in pts]

    def _prepare_geometry(self, shape):
        if self._shape == shape[:2]:
            return
        self._shape = shape[:2]
        for z in self.zones:
            z["_px"] = self._px(z["points"], shape)
        if self.calib.get("mode") == "homography" and len(self.calib.get("image_points") or []) == 4:
            src = np.float32(self._px(self.calib["image_points"], shape))
            dst = np.float32(self.calib["world_points"])
            self._homography = cv2.getPerspectiveTransform(src, dst)
        for key in ("line_a", "line_b"):
            if len(self.calib.get(key) or []) == 2:
                self.calib["_" + key] = self._px(self.calib[key], shape)

    def _zones_at(self, x, y):
        return [z for z in self.zones if point_in_polygon(x, y, z["_px"])]

    # ------------------------------------------------------------------ main entry
    def process(self, frame, ts=None):
        ts = ts or time.time()
        self.frame_no += 1
        self._prepare_geometry(frame.shape)
        eng = self.engines

        if eng.vehicle is not None:
            dets = eng.vehicle.detect(frame, imgsz=int(self.cfg["imgsz"]))
        else:
            dets = self._plate_only_detections(frame)
        active, finished = self.tracker.update(dets, ts)

        frame_plates = None
        if self.cfg["detect_plates"] and eng.plate is not None and self.cfg["plate_mode"] == "frame" \
                and self.frame_no % 2 == 0:
            frame_plates = eng.plate.read(frame)

        visible = [t for t in active if t.missed == 0]  # matched in this frame
        for t in visible:
            self._update_track(t, frame, ts, frame_plates)
        self._parking_logic(active, frame, ts)

        for t in finished:
            self._finish(t)
        return self._annotate(frame, visible)

    def close(self):
        for t in self.tracker.flush():
            self._finish(t)

    # ------------------------------------------------------------------ per track
    def _plate_only_detections(self, frame):
        """No vehicle model: treat each plate as a vehicle (dedicated ANPR cameras)."""
        if self.engines.plate is None or self.frame_no % 2:
            return [(t.box, "car", t.conf) for t in self.tracker.tracks.values()]
        out = []
        for p in self.engines.plate.read(frame):
            x1, y1, x2, y2 = p["bbox"]
            w, h = x2 - x1, y2 - y1
            out.append(((max(0, x1 - 2 * w), max(0, y1 - 5 * h), x2 + 2 * w, y2 + h), "car", 0.5))
        return out

    def _update_track(self, t, frame, ts, frame_plates):
        fh, fw = frame.shape[:2]
        vtype = refine_type(t.labels.most_common(1)[0][0], t.box, frame.shape, self.size_ref)
        t.types[vtype] += 1
        x, y = t.bottom_center

        # zones
        inside = {z["name"] for z in self._zones_at(x, y)}
        for name in list(t.zone_times):
            if name not in inside:
                t.zone_times.pop(name)
        for name in inside:
            t.zone_times.setdefault(name, ts)

        # speed
        self._speed(t)

        # stationary state
        width = max(t.box[2] - t.box[0], 1)
        if ts - t.first_ts >= self.cfg["stationary_window"] and \
                t.displacement(self.cfg["stationary_window"]) < 0.12 * width:
            if t.stationary_since is None:
                t.stationary_since = ts - self.cfg["stationary_window"]
        else:
            t.stationary_since = None

        vcrop = None
        if t.hits % 3 == 1 or t.hits <= 2:
            vcrop = crop(frame, t.box)
            color, share = classify_color(vcrop)
            if color != "unknown":
                t.colors[color] += share
            attr = self.engines.attr.predict(vcrop) if self.engines.attr else None
            if attr:
                t.types[attr["vehicle_type"]] += 3 * attr["conf"]
                if attr["loaded"] != "unknown":
                    t.loaded[attr["loaded"]] += 3 * attr["conf"]
            else:
                cur = t.types.most_common(1)[0][0]
                if cur in CARGO_TYPES:
                    state, _ = estimate_loaded(vcrop, cur)
                    if state != "unknown":
                        t.loaded[state] += 1

        # plates (keep re-verifying after confirmation to catch identity switches)
        plate_found = None
        confirmed = self._plate_confirmed(t)
        if self.cfg["detect_plates"] and self.engines.plate is not None:
            if frame_plates is not None:
                inside = [p for p in frame_plates if t.box[0] <= (p["bbox"][0] + p["bbox"][2]) / 2 <= t.box[2]
                          and t.box[1] <= (p["bbox"][1] + p["bbox"][3]) / 2 <= t.box[3]]
                plate_found = self._closest_plate(t, inside)
            elif width >= self.cfg["min_plate_width"] * 2 and (
                    (not confirmed and t.plate_attempts < self.cfg["plate_max_attempts"] and (t.hits % 2 == 0 or t.hits <= 2))
                    or (confirmed and t.hits % 6 == 0)):
                t.plate_attempts += 1
                pad = 0.06
                region = crop(frame, t.box, pad)
                ox = max(0, int(t.box[0] - (t.box[2] - t.box[0]) * pad))
                oy = max(0, int(t.box[1] - (t.box[3] - t.box[1]) * pad))
                found = []
                for p in self.engines.plate.read(region):
                    x1, y1, x2, y2 = p["bbox"]
                    p["bbox"] = (x1 + ox, y1 + oy, x2 + ox, y2 + oy)
                    found.append(p)
                plate_found = self._closest_plate(t, found)
            if plate_found is not None and self._identity_switch(t, plate_found, confirmed):
                return self._split(t, frame, ts, plate_found)
            if plate_found is not None:
                t.plates.append(plate_found)

        # best snapshot: prefer frames with a plate read, then larger boxes
        area = (t.box[2] - t.box[0]) * (t.box[3] - t.box[1])
        score = area * (3 if plate_found else 1)
        key = plate_found["raw_text"] if plate_found else None
        prev = t.best_by_plate.get(key) if key else t.best
        if prev is None or score > prev[0] * 1.15:
            vcrop = vcrop if vcrop is not None else crop(frame, t.box)
            snap = frame.copy()
            cv2.rectangle(snap, t.box[:2], t.box[2:], (0, 220, 255), 3)
            pimg = None
            if plate_found:
                pimg = encode_jpeg(crop(frame, plate_found["bbox"], 0.15), 90)
                cv2.rectangle(snap, plate_found["bbox"][:2], plate_found["bbox"][2:], (0, 0, 255), 2)
            evidence = (score, encode_jpeg(snap, 80, 1600), encode_jpeg(vcrop, 88), pimg)
            if key:
                t.best_by_plate[key] = evidence
            else:
                t.best = evidence

    @staticmethod
    def _closest_plate(t, plates):
        """The plate belonging to this vehicle: nearest to the bottom-centre of its box."""
        bx, by = t.bottom_center
        h = max(t.box[3] - t.box[1], 1)
        # plates sit on the lower part of a vehicle; anything higher belongs to a vehicle behind it
        plates = [p for p in plates if p["bbox"][1] > t.box[1] + 0.25 * h]
        if not plates:
            return None
        return min(plates, key=lambda p: abs((p["bbox"][0] + p["bbox"][2]) / 2 - bx) + 0.5 * abs(p["bbox"][3] - by))

    def _identity_switch(self, t, plate, confirmed):
        if not confirmed or plate["char_conf_avg"] < 0.7:
            t.foreign_reads = 0
            return False
        current = Counter(p["raw_text"] for p in t.plates).most_common(1)[0][0]
        from difflib import SequenceMatcher

        if SequenceMatcher(None, current, plate["raw_text"]).ratio() >= 0.7:
            t.foreign_reads = 0
            return False
        t.foreign_reads += 1
        return t.foreign_reads >= 2

    def _split(self, t, frame, ts, plate):
        """The tracker merged two vehicles: report the first one and continue with a new identity."""
        fresh = t.split(ts)
        self._finish(t)
        self.tracker.tracks.pop(t.id, None)
        self.tracker.tracks[fresh.id] = fresh
        fresh.plates.append(plate)
        self.stats["identity_switch"] += 1

    def _plate_confirmed(self, t):
        if not t.plates:
            return False
        counts = Counter(p["raw_text"] for p in t.plates)
        text, n = counts.most_common(1)[0]
        best_conf = max(p["char_conf_avg"] for p in t.plates if p["raw_text"] == text)
        return n >= 2 or best_conf >= 0.9

    def _speed(self, t):
        if len(t.history) < 2:
            return
        _, x0, y0 = t.history[-2]
        ts, x1, y1 = t.history[-1]
        la, lb = self.calib.get("_line_a"), self.calib.get("_line_b")
        dist = float(self.calib.get("distance_m") or 0)
        if la and lb and dist > 0:
            for key, line in (("a", la), ("b", lb)):
                if key not in t.line_hits and segments_cross((x0, y0), (x1, y1), line[0], line[1]):
                    t.line_hits[key] = ts
            if "a" in t.line_hits and "b" in t.line_hits and t.speed is None:
                dt = abs(t.line_hits["b"] - t.line_hits["a"])
                if dt > 0.15:
                    speed = dist / dt * 3.6
                    if speed < 260:
                        t.speed = speed
                        t.direction = "a_to_b" if t.line_hits["a"] < t.line_hits["b"] else "b_to_a"
        elif self._homography is not None and len(t.history) >= 6:
            pts = list(t.history)[-12:]
            if pts[-1][0] - pts[0][0] < 0.5:
                return
            arr = np.float32([[[p[1], p[2]]] for p in (pts[0], pts[-1])])
            world = cv2.perspectiveTransform(arr, self._homography).reshape(-1, 2)
            meters = float(np.linalg.norm(world[1] - world[0]))
            speed = meters / (pts[-1][0] - pts[0][0]) * 3.6
            if 3 < speed < 260:
                t.speed = speed if t.speed is None else 0.7 * t.speed + 0.3 * speed

    # ------------------------------------------------------------------ parking behaviour
    def _parking_logic(self, active, frame, ts):
        if not self.zones:
            return
        zone_by_name = {z["name"]: z for z in self.zones}
        moving_traffic = any(t.stationary_since is None and t.displacement(3) > 0.3 * (t.box[2] - t.box[0])
                             for t in active)
        for t in active:
            if t.stationary_since is None or t.hits < self.cfg["min_hits"]:
                continue
            still = ts - t.stationary_since
            for name, since in t.zone_times.items():
                zone = zone_by_name.get(name)
                if not zone:
                    continue
                ztype = zone.get("type")
                dwell = min(still, ts - since)
                key = f"{ztype}:{name}"
                if key in t.state_emitted:
                    continue
                if ztype == "curb_parking" and dwell >= self.cfg["park_seconds"]:
                    t.state_emitted.add(key)
                    self._emit(t, "parking", zone, dwell)
                elif ztype == "no_parking" and dwell >= self.cfg["no_parking_seconds"]:
                    t.state_emitted.add(key)
                    self._emit(t, "no_parking", zone, dwell)
                elif ztype == "traffic_lane" and dwell >= self.cfg["double_parking_seconds"] and moving_traffic:
                    neighbour = self._parked_neighbour(t, active)
                    t.state_emitted.add(key)
                    self._emit(t, "double_parking" if neighbour else "stopped", zone, dwell,
                               neighbour_track=neighbour.id if neighbour else None)

    def _parked_neighbour(self, t, active):
        w = t.box[2] - t.box[0]
        for o in active:
            if o is t or o.stationary_since is None:
                continue
            in_curb = any(z.get("type") == "curb_parking" for z in self.zones if z["name"] in o.zone_times)
            horizontal_gap = max(o.box[0] - t.box[2], t.box[0] - o.box[2], 0)
            vertical_overlap = min(t.box[3], o.box[3]) - max(t.box[1], o.box[1])
            if (in_curb or o.stationary_since < t.stationary_since) and horizontal_gap < 0.6 * w \
                    and vertical_overlap > 0:
                return o
        return None

    # ------------------------------------------------------------------ emission
    def _finish(self, t):
        if t.hits < self.cfg["min_hits"] or t.emitted_passage:
            return
        if t.state_emitted:  # already reported as parked/stopped vehicle
            return
        zone_type = None
        for name in t.zone_times:
            for z in self.zones:
                if z["name"] == name and z.get("type") == "bus_lane":
                    zone_type = "bus_lane"
        t.emitted_passage = True
        self._emit(t, "passage", {"name": None, "type": zone_type}, t.last_ts - t.first_ts)

    def _emit(self, t, kind, zone, dwell, **extra):
        vtype = t.types.most_common(1)[0][0] if t.types else "unknown"
        plate = None
        if t.plates:
            counts = Counter(p["raw_text"] for p in t.plates)
            text, _ = counts.most_common(1)[0]
            plate = max((p for p in t.plates if p["raw_text"] == text), key=lambda p: p["char_conf_avg"])
        loaded = "unknown"
        if vtype in CARGO_TYPES and t.loaded:
            state, votes = t.loaded.most_common(1)[0]
            if votes >= 2:
                loaded = state
        if plate and plate_utils.category(plate["raw_text"]) == "taxi" and vtype == "car":
            vtype = "taxi"
        evidence = t.best_by_plate.get(plate["raw_text"]) if plate else None
        if evidence is None and t.best_by_plate and not plate:
            evidence = max(t.best_by_plate.values(), key=lambda e: e[0])
        best = evidence or t.best or (0, None, None, None)
        obs = {
            "camera_id": self.cam.get("id"),
            "district_id": self.cam.get("district_id"),
            "ts": t.last_ts,
            "kind": kind,
            "plate": plate["raw_text"] if plate else None,
            "plate_type": plate["plate_type"] if plate else None,
            "plate_conf": plate["char_conf_avg"] if plate else None,
            "vehicle_type": vtype,
            "is_heavy": vtype in HEAVY_TYPES,
            "is_pickup": vtype == "pickup",
            "loaded": loaded,
            "color": t.colors.most_common(1)[0][0] if t.colors else "unknown",
            "speed_kmh": round(t.speed, 1) if t.speed else None,
            "direction": t.direction,
            "dwell_seconds": round(dwell, 1) if dwell else None,
            "zone": zone.get("name"),
            "zone_type": zone.get("type"),
            "confidence": round(t.conf, 3),
            "images": {"frame": best[1], "vehicle": best[2], "plate": best[3]},
            "attrs": {"track_id": t.id, "hits": t.hits, "plate_reads": len(t.plates),
                      "coco": t.label, **({k: v for k, v in extra.items() if v is not None})},
        }
        self.stats[kind] += 1
        try:
            self.sink(obs)
        except Exception:
            log.exception("sink failed for camera %s", self.cam.get("id"))

    # ------------------------------------------------------------------ preview
    def _annotate(self, frame, active):
        out = frame.copy()
        overlay = out.copy()
        for z in self.zones:
            pts = np.int32(z["_px"])
            color = ZONE_COLORS.get(z.get("type"), (200, 200, 200))
            cv2.fillPoly(overlay, [pts], color)
            cv2.polylines(out, [pts], True, color, 2)
        cv2.addWeighted(overlay, 0.18, out, 0.82, 0, out)
        for key, color in (("_line_a", (255, 255, 0)), ("_line_b", (255, 0, 255))):
            line = self.calib.get(key)
            if line:
                cv2.line(out, tuple(map(int, line[0])), tuple(map(int, line[1])), color, 2)
        for t in active:
            vtype = t.types.most_common(1)[0][0] if t.types else t.label
            color = TYPE_COLORS.get(vtype, (255, 200, 60))
            if t.stationary_since is not None:
                color = (0, 140, 255)
            x1, y1, x2, y2 = t.box
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            parts = [f"#{t.id} {vtype}"]
            if t.plates:
                parts.append(Counter(p["raw_text"] for p in t.plates).most_common(1)[0][0])
            if t.speed:
                parts.append(f"{t.speed:.0f}km/h")
            label = " | ".join(parts)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(out, (x1, max(0, y1 - th - 8)), (x1 + tw + 6, y1), color, -1)
            cv2.putText(out, label, (x1 + 3, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1, cv2.LINE_AA)
        return out
