import threading
import time
from collections import Counter, deque
from difflib import SequenceMatcher

import cv2
import torch

from configParams import Parameters
from helper.plate_recognition import recognize_plates
from helper.text_decorators import (
    clean_license_plate_text,
    format_license_plate_label,
    format_license_plate_persian,
)

from lite.image_utils import draw_plates, prepare_frame
from lite.plate_validation import accept_plate_detection, plate_group_key

TYPE_LABELS = {"national": "ملی", "freezone": "منطقه آزاد", "unknown": "نامشخص"}


class PlateReader:
    """Loads models once and runs the full-quality recognition pipeline."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self, plate_conf=0.25, char_conf=0.25):
        self.plate_conf = plate_conf
        self.char_conf = char_conf
        self.params = Parameters()
        self.model_plate = torch.hub.load(
            "yolov5",
            "custom",
            self.params.modelPlate_path,
            source="local",
            force_reload=False,
        )
        self.model_char = torch.hub.load(
            "yolov5",
            "custom",
            self.params.modelCharX_path,
            source="local",
            force_reload=False,
        )
        self.model_plate.conf = plate_conf
        self.model_char.conf = plate_conf

    @classmethod
    def get(cls, plate_conf=0.25, char_conf=0.25):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(plate_conf=plate_conf, char_conf=char_conf)
            return cls._instance

    def recognize_bgr(self, frame_bgr):
        rgb = prepare_frame(frame_bgr)
        raw_plates = recognize_plates(
            rgb,
            self.model_plate,
            self.model_char,
            self.params,
            self.plate_conf,
            self.char_conf,
        )
        return self._format_results(raw_plates)

    def _format_results(self, raw_plates):
        plates = []
        for plate in raw_plates:
            plate_type = plate.get("plate_type", "unknown")
            raw_text = plate["raw_text"]
            formatted = {
                "raw_text": raw_text,
                "clean_text": clean_license_plate_text(
                    raw_text, plate_type=plate_type
                ),
                "persian_text": format_license_plate_persian(
                    raw_text, plate_type=plate_type
                ),
                "label": format_license_plate_label(
                    raw_text, plate_type=plate_type
                ),
                "plate_type": plate_type,
                "plate_type_label": TYPE_LABELS.get(plate_type, "نامشخص"),
                "plate_conf": round(float(plate["plate_conf"]), 4),
                "char_conf_avg": round(float(plate["char_conf_avg"]), 4),
                "bbox": plate["bbox"],
            }
            accepted = accept_plate_detection(formatted)
            if accepted:
                plates.append(accepted)
        return plates


class PlateVoteBuffer:
    """Collect recent reads and return a stable plate text without lowering OCR quality."""

    def __init__(self, window=5, min_similarity=0.72, min_char_conf=0.45):
        self.window = window
        self.min_similarity = min_similarity
        self.min_char_conf = min_char_conf
        self._items = deque(maxlen=window)

    def add(self, plates):
        for plate in plates:
            if plate["char_conf_avg"] >= self.min_char_conf:
                self._items.append(plate)

    def best(self):
        if not self._items:
            return None

        texts = [item["raw_text"] for item in self._items]
        counter = Counter(texts)
        raw_text, count = counter.most_common(1)[0]
        if count >= 2:
            for item in reversed(self._items):
                if item["raw_text"] == raw_text:
                    return item

        best_item = None
        best_score = -1.0
        for candidate in self._items:
            matches = sum(
                1
                for other in texts
                if SequenceMatcher(None, candidate["raw_text"], other).ratio()
                >= self.min_similarity
            )
            score = matches * candidate["char_conf_avg"]
            if score > best_score:
                best_score = score
                best_item = candidate
        return best_item


def open_capture(source):
    if source.isdigit():
        return cv2.VideoCapture(int(source))
    return cv2.VideoCapture(source, cv2.CAP_FFMPEG)


def iter_video_frames(capture, frame_skip=1):
    frame_id = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        frame_id += 1
        if frame_id % frame_skip == 0:
            yield frame_id, frame


def process_image_file(reader, path):
    frame = cv2.imread(path)
    if frame is None:
        raise FileNotFoundError(f"Cannot read image: {path}")
    plates = reader.recognize_bgr(frame)
    annotated = draw_plates(frame, plates)
    return plates, annotated


def process_video_file(reader, path, frame_skip=5, output_path=None):
    capture = open_capture(path)
    if not capture.isOpened():
        raise FileNotFoundError(f"Cannot open video: {path}")

    writer = None
    all_results = []
    try:
        for frame_id, frame in iter_video_frames(capture, frame_skip=frame_skip):
            plates = reader.recognize_bgr(frame)
            if plates:
                all_results.append({"frame": frame_id, "plates": plates})
            if output_path:
                annotated = draw_plates(frame, plates)
                if writer is None:
                    height, width = annotated.shape[:2]
                    writer = cv2.VideoWriter(
                        output_path,
                        cv2.VideoWriter_fourcc(*"mp4v"),
                        5,
                        (width, height),
                    )
                writer.write(annotated)
    finally:
        capture.release()
        if writer is not None:
            writer.release()
    return all_results


def _plate_group_key(plate):
    return plate_group_key(plate)


def iter_video_plate_events(reader, path, frame_skip=5):
    """Yield grouped video events: new plate screenshot or repeat counter bump."""
    import base64

    capture = open_capture(path)
    if not capture.isOpened():
        raise FileNotFoundError(f"Cannot open video: {path}")

    current_key = None
    current_count = 0
    unique_keys = set()
    total_hits = 0

    try:
        for frame_id, frame in iter_video_frames(capture, frame_skip=frame_skip):
            yield {"type": "progress", "frame": frame_id, "status": "scanning"}

            plates = reader.recognize_bgr(frame)
            if not plates:
                yield {"type": "progress", "frame": frame_id, "status": "no_plate"}
                continue

            plate = plates[0]
            key = _plate_group_key(plate)
            if not key:
                yield {"type": "progress", "frame": frame_id, "status": "no_plate"}
                continue

            total_hits += 1
            unique_keys.add(key)

            if key == current_key:
                current_count += 1
                yield {
                    "type": "repeat",
                    "key": key,
                    "count": current_count,
                    "frame": frame_id,
                    "plate": plate,
                }
                continue

            current_key = key
            current_count = 1
            annotated = draw_plates(frame, [plate])
            ok, encoded = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            yield {
                "type": "new_plate",
                "key": key,
                "count": 1,
                "frame": frame_id,
                "plate": plate,
                "image_base64": base64.b64encode(encoded.tobytes()).decode("ascii") if ok else None,
            }
    finally:
        capture.release()

    yield {
        "type": "done",
        "unique_plates": len(unique_keys),
        "total_hits": total_hits,
    }


def run_camera_loop(
    reader,
    source,
    frame_skip=5,
    vote_window=5,
    on_plate=None,
    preview=False,
):
    capture = open_capture(source)
    if not capture.isOpened():
        raise RuntimeError(f"Cannot open camera source: {source}")

    vote_buffer = PlateVoteBuffer(window=vote_window)
    last_emit = {}

    try:
        frame_id = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                time.sleep(0.2)
                continue

            frame_id += 1
            plates = []
            if frame_id % frame_skip == 0:
                plates = reader.recognize_bgr(frame)
                vote_buffer.add(plates)
                stable = vote_buffer.best()
                if stable and on_plate:
                    now = time.time()
                    key = stable["raw_text"]
                    if now - last_emit.get(key, 0) >= 3.0:
                        last_emit[key] = now
                        on_plate(stable, frame)

            if preview:
                display = draw_plates(frame, plates)
                cv2.imshow("plpr-lite", display)
                if cv2.waitKey(1) == 27:
                    break
    finally:
        capture.release()
        if preview:
            cv2.destroyAllWindows()
