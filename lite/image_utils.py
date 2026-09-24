import cv2
import numpy as np
from PIL import Image, ImageOps


def prepare_frame(frame_bgr):
    """Same preprocessing as streamlit_app — no PySide6 dependency."""
    height, width = frame_bgr.shape[:2]
    max_dim = max(height, width)

    if max_dim > 1920:
        scale = 1920 / max_dim
        frame_bgr = cv2.resize(
            frame_bgr,
            (int(width * scale), int(height * scale)),
            interpolation=cv2.INTER_AREA,
        )
    elif max_dim < 640:
        scale = 640 / max_dim
        frame_bgr = cv2.resize(
            frame_bgr,
            (int(width * scale), int(height * scale)),
            interpolation=cv2.INTER_CUBIC,
        )

    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    enhanced = ImageOps.autocontrast(Image.fromarray(rgb), cutoff=1)
    return np.array(enhanced)


def draw_plates(frame_bgr, plates):
    output = frame_bgr.copy()
    for plate in plates:
        x1, y1, x2, y2 = plate["bbox"]
        cv2.rectangle(output, (x1, y1), (x2, y2), (0, 0, 255), 2)
        label = plate.get("label") or plate.get("raw_text") or "?"
        cv2.putText(
            output,
            label,
            (x1, max(y1 - 8, 16)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
        )
    return output
