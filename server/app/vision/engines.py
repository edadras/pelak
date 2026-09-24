"""Model wrappers shared by all cameras handled by one worker process."""
import logging
import os
import sys
import threading

import cv2
import numpy as np

from app.config import settings
from app.core import plates as plate_utils

log = logging.getLogger(__name__)

COCO_VEHICLES = {1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


class VehicleDetector:
    def __init__(self, weights=None, device=None, conf=None):
        from ultralytics import YOLO

        self.model = YOLO(weights or settings.vehicle_model)
        self.device = device or settings.device
        self.conf = conf or settings.vehicle_conf
        self.lock = threading.Lock()
        names = self.model.names
        # Custom detectors may use their own names: keep any class whose name we understand
        self.class_map = {}
        for idx, name in names.items():
            if idx in COCO_VEHICLES and name == COCO_VEHICLES[idx]:
                self.class_map[idx] = name
            elif name in ("car", "truck", "bus", "motorcycle", "bicycle", "pickup", "van", "trailer"):
                self.class_map[idx] = name

    def detect(self, frame_bgr, imgsz=640):
        with self.lock:
            res = self.model.predict(frame_bgr, imgsz=imgsz, conf=self.conf, device=self.device,
                                     classes=list(self.class_map), verbose=False)[0]
        out = []
        if res.boxes is None:
            return out
        for box, cls, conf in zip(res.boxes.xyxy.cpu().numpy(), res.boxes.cls.cpu().numpy(),
                                  res.boxes.conf.cpu().numpy()):
            label = self.class_map.get(int(cls))
            if label:
                out.append((tuple(int(v) for v in box), label, float(conf)))
        return _nms_cross_class(out)


def _nms_cross_class(dets, thr=0.7):
    """YOLO NMS is per class; the same vehicle can be both 'car' and 'truck'. Keep the best."""
    from app.vision.geometry import iou

    dets = sorted(dets, key=lambda d: -d[2])
    kept = []
    for d in dets:
        if all(iou(d[0], k[0]) < thr for k in kept):
            kept.append(d)
    return kept


class PlateEngine:
    """Wraps the repository's proven plate pipeline (lite.reader.PlateReader)."""

    def __init__(self):
        repo = str(settings.plate_repo_dir)
        if repo not in sys.path:
            sys.path.insert(0, repo)
        # configParams reads ./config.ini and torch.hub loads ./yolov5 relative to the cwd
        prev = os.getcwd()
        os.chdir(repo)
        try:
            from lite.reader import PlateReader

            self.reader = PlateReader(plate_conf=settings.plate_conf, char_conf=settings.char_conf)
        finally:
            os.chdir(prev)
        self.lock = threading.Lock()

    def read(self, image_bgr):
        """Return list of plates (bbox in image_bgr pixel coords)."""
        if image_bgr is None or image_bgr.size == 0:
            return []
        h, w = image_bgr.shape[:2]
        # PlateReader.prepare_frame rescales to 640..1920 px on the longest side; map boxes back
        max_dim = max(h, w)
        scale = 1920 / max_dim if max_dim > 1920 else (640 / max_dim if max_dim < 640 else 1.0)
        with self.lock:
            found = self.reader.recognize_bgr(image_bgr)
        out = []
        for p in found:
            x1, y1, x2, y2 = p["bbox"]
            p = dict(p)
            p["bbox"] = (int(x1 / scale), int(y1 / scale), int(x2 / scale), int(y2 / scale))
            p["fa"] = plate_utils.format_fa(p["raw_text"])
            out.append(p)
        return out


class Engines:
    """Lazily loaded, process-wide model set. Missing components degrade gracefully."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        from app.vision.attributes import AttributeModel

        self.vehicle = None
        self.plate = None
        self.errors = {}
        try:
            self.vehicle = VehicleDetector()
            log.info("vehicle detector ready (%s on %s)", settings.vehicle_model, settings.device)
        except Exception as exc:
            self.errors["vehicle"] = str(exc)
            log.exception("vehicle detector unavailable")
        try:
            self.plate = PlateEngine()
            log.info("plate engine ready")
        except Exception as exc:
            self.errors["plate"] = str(exc)
            log.exception("plate engine unavailable")
        self.attr = AttributeModel(settings.attr_model, settings.device)

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance


def encode_jpeg(img, quality=82, max_width=None):
    if img is None or img.size == 0:
        return None
    if max_width and img.shape[1] > max_width:
        s = max_width / img.shape[1]
        img = cv2.resize(img, (max_width, int(img.shape[0] * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buf.tobytes() if ok else None


def crop(img, box, pad=0.0):
    h, w = img.shape[:2]
    x1, y1, x2, y2 = box
    px, py = (x2 - x1) * pad, (y2 - y1) * pad
    x1, y1 = max(0, int(x1 - px)), max(0, int(y1 - py))
    x2, y2 = min(w, int(x2 + px)), min(h, int(y2 + py))
    if x2 <= x1 or y2 <= y1:
        return np.zeros((0, 0, 3), np.uint8)
    return img[y1:y2, x1:x2]
