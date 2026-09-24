"""Vehicle colour, fine-grained type, heavy/pickup and loaded-state estimation.

A dedicated classification model (``ATTR_MODEL``, Ultralytics classify format) is used when
present — see ``tools/train_vehicle_attributes.py``. Otherwise robust heuristics are used.
"""
import logging
import os
import threading
from collections import deque

import cv2
import numpy as np

from app.core.vehicles import HEAVY_TYPES

log = logging.getLogger(__name__)

# Model class name -> (vehicle_type, loaded)
ATTR_CLASSES = {
    "sedan": ("car", "unknown"), "hatchback": ("car", "unknown"), "car": ("car", "unknown"),
    "suv": ("suv", "unknown"), "taxi": ("taxi", "unknown"), "van": ("van", "unknown"),
    "pickup_empty": ("pickup", "empty"), "pickup_loaded": ("pickup", "loaded"),
    "light_truck_empty": ("light_truck", "empty"), "light_truck_loaded": ("light_truck", "loaded"),
    "truck_empty": ("truck", "empty"), "truck_loaded": ("truck", "loaded"),
    "trailer_empty": ("trailer", "empty"), "trailer_loaded": ("trailer", "loaded"),
    "minibus": ("minibus", "unknown"), "bus": ("bus", "unknown"),
    "motorcycle": ("motorcycle", "unknown"), "bicycle": ("bicycle", "unknown"),
}


def classify_color(crop_bgr):
    """Dominant body colour of a vehicle crop -> key of app.core.vehicles.COLORS."""
    if crop_bgr is None or crop_bgr.size == 0:
        return "unknown", 0.0
    h, w = crop_bgr.shape[:2]
    body = crop_bgr[int(h * 0.35): int(h * 0.85), int(w * 0.15): int(w * 0.85)]
    if body.size == 0:
        return "unknown", 0.0
    body = cv2.resize(body, (64, 48), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(body, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)
    hue, sat, val = hsv[:, 0] * 2, hsv[:, 1] / 255, hsv[:, 2] / 255

    labels = np.empty(len(hue), dtype=object)
    achrom = (sat < 0.22) | (val < 0.18)
    labels[achrom & (val < 0.22)] = "black"
    labels[achrom & (val >= 0.22) & (val < 0.50)] = "gray"
    labels[achrom & (val >= 0.50) & (val < 0.75)] = "silver"
    labels[achrom & (val >= 0.75)] = "white"
    chrom = ~achrom
    bins = [(0, 12, "red"), (12, 38, "orange"), (38, 70, "yellow"), (70, 170, "green"),
            (170, 260, "blue"), (260, 330, "red"), (330, 361, "red")]
    for lo, hi, name in bins:
        labels[chrom & (hue >= lo) & (hue < hi)] = name
    # dark orange / low value warm hues read as brown/beige
    labels[chrom & (hue < 45) & (val < 0.55)] = "brown"
    labels[chrom & (hue < 45) & (sat < 0.40) & (val >= 0.55)] = "brown"

    names, counts = np.unique(labels.astype(str), return_counts=True)
    order = np.argsort(-counts)
    best = names[order[0]]
    share = counts[order[0]] / counts.sum()
    # Coloured paint usually covers less area than glass/shadows: prefer a strong chromatic share
    for idx in order[1:3]:
        if names[idx] not in ("black", "gray", "silver", "white") and counts[idx] / counts.sum() > 0.30 \
                and best in ("black", "gray"):
            best, share = names[idx], counts[idx] / counts.sum()
            break
    return str(best), float(share)


class SizeReference:
    """Running median of car box areas per image row band, to judge relative vehicle size."""

    def __init__(self, bands=6):
        self.bands = bands
        self.samples = [deque(maxlen=60) for _ in range(bands)]

    def _band(self, y_norm):
        return min(self.bands - 1, max(0, int(y_norm * self.bands)))

    def add_car(self, box, frame_h):
        area = (box[2] - box[0]) * (box[3] - box[1])
        self.samples[self._band(box[3] / frame_h)].append(area)

    def ratio(self, box, frame_h):
        band = self._band(box[3] / frame_h)
        data = self.samples[band]
        if len(data) < 5:  # borrow from neighbours
            for off in (1, -1, 2, -2):
                b = band + off
                if 0 <= b < self.bands and len(self.samples[b]) >= 5:
                    data = self.samples[b]
                    break
        if len(data) < 5:
            return None
        area = (box[2] - box[0]) * (box[3] - box[1])
        return area / float(np.median(data))


def refine_type(coco_label, box, frame_shape, size_ref: SizeReference):
    """Map a COCO class to the Iranian traffic vocabulary using relative size."""
    fh, fw = frame_shape[:2]
    w, h = box[2] - box[0], box[3] - box[1]
    ratio = size_ref.ratio(box, fh)
    if coco_label == "car":
        size_ref.add_car(box, fh)
        if ratio and ratio > 1.7 and h / max(w, 1) > 0.85:
            return "van"
        return "car"
    if coco_label == "motorcycle":
        return "motorcycle"
    if coco_label == "bicycle":
        return "bicycle"
    if coco_label == "bus":
        if ratio is not None and ratio < 2.6:
            return "minibus"
        return "bus"
    if coco_label == "truck":
        if ratio is None:
            rel = (w * h) / float(fw * fh)
            return "pickup" if rel < 0.06 else "truck"
        if ratio < 1.8:
            return "pickup"
        if ratio < 3.2:
            return "light_truck"
        if ratio < 7 or w / max(h, 1) < 2.2:
            return "truck"
        return "trailer"
    return "unknown"


def estimate_loaded(crop_bgr, vehicle_type):
    """Heuristic load detection for cargo vehicles.

    Looks at the cargo area (rear/top part of the box). An empty bed shows a flat, low-texture
    region; cargo adds edges, texture and colour variation above the bed rails.
    Returns ("loaded"|"empty"|"unknown", score).
    """
    if vehicle_type not in ("pickup", "light_truck", "truck", "trailer") or crop_bgr is None:
        return "unknown", 0.0
    h, w = crop_bgr.shape[:2]
    if h < 40 or w < 40:
        return "unknown", 0.0
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    top = gray[: int(h * 0.45), :]
    edges = cv2.Canny(top, 60, 160)
    edge_density = edges.mean() / 255.0
    texture = float(cv2.Laplacian(top, cv2.CV_64F).var()) / 1000.0
    hsv = cv2.cvtColor(crop_bgr[: int(h * 0.45), :], cv2.COLOR_BGR2HSV)
    color_var = float(hsv[:, :, 0].std()) / 90.0
    score = 0.55 * min(edge_density / 0.12, 1.5) + 0.25 * min(texture, 1.5) + 0.20 * min(color_var, 1.5)
    if score > 0.85:
        return "loaded", score
    if score < 0.45:
        return "empty", score
    return "unknown", score


class AttributeModel:
    """Optional fine-grained classifier (Ultralytics classification weights)."""

    def __init__(self, path, device="cpu"):
        self.model = None
        self.lock = threading.Lock()
        self.device = device
        if path and os.path.exists(path):
            try:
                from ultralytics import YOLO

                self.model = YOLO(path)
                log.info("vehicle attribute model loaded: %s", path)
            except Exception as exc:  # pragma: no cover
                log.warning("attribute model load failed: %s", exc)

    def predict(self, crop_bgr):
        if self.model is None or crop_bgr is None or crop_bgr.size == 0:
            return None
        with self.lock:
            res = self.model.predict(crop_bgr, verbose=False, device=self.device, imgsz=224)[0]
        name = res.names[int(res.probs.top1)]
        conf = float(res.probs.top1conf)
        mapped = ATTR_CLASSES.get(name)
        if not mapped or conf < 0.5:
            return None
        vtype, loaded = mapped
        return {"vehicle_type": vtype, "loaded": loaded, "conf": conf,
                "heavy": vtype in HEAVY_TYPES}
