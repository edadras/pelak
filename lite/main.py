"""PLPR Lite — lightweight API for image, video, and camera plate recognition."""

import asyncio
import base64
import json
import os
import queue
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lite.image_utils import draw_plates
from lite.reader import (
    PlateReader,
    iter_video_plate_events,
    open_capture,
    process_video_file,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
OUTPUT_DIR = Path(os.getenv("LITE_OUTPUT_DIR", "/output"))
DATA_DIR = Path(os.getenv("LITE_DATA_DIR", "/data"))

PLATE_CONF = float(os.getenv("PLATE_CONF", "0.25"))
CHAR_CONF = float(os.getenv("CHAR_CONF", "0.25"))
FRAME_SKIP = int(os.getenv("LITE_FRAME_SKIP", "5"))
VOTE_WINDOW = int(os.getenv("LITE_VOTE_WINDOW", "5"))

STREAM_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

reader = None
camera_thread = None
camera_stop = threading.Event()
latest_camera_frame = None
latest_camera_plates = []
camera_lock = threading.Lock()


def env_source():
    return os.getenv("LITE_SOURCE", "").strip()


def env_mode():
    return os.getenv("LITE_MODE", "server").strip().lower()


@asynccontextmanager
async def lifespan(_app):
    global reader
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    reader = PlateReader.get(plate_conf=PLATE_CONF, char_conf=CHAR_CONF)
    mode = env_mode()
    if mode in {"camera", "rtsp", "webcam"}:
        source = env_source() or os.getenv("LITE_RTSP", "0")
        start_camera_worker(source)
    yield
    stop_camera_worker()


app = FastAPI(title="PLPR Lite", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def plate_to_dict(plate):
    return {
        "raw_text": plate["raw_text"],
        "clean_text": plate["clean_text"],
        "persian_text": plate["persian_text"],
        "label": plate["label"],
        "plate_type": plate["plate_type"],
        "plate_type_label": plate["plate_type_label"],
        "plate_conf": plate["plate_conf"],
        "char_conf_avg": plate["char_conf_avg"],
        "bbox": list(plate["bbox"]),
    }


def _camera_worker(source):
    global latest_camera_frame, latest_camera_plates

    def on_plate(stable, frame):
        with camera_lock:
            latest_camera_plates = [stable]
            latest_camera_frame = draw_plates(frame, [stable])

    capture = open_capture(source)
    if not capture.isOpened():
        print(f"Camera source unavailable: {source}", flush=True)
        return

    from lite.reader import PlateVoteBuffer

    vote_buffer = PlateVoteBuffer(window=VOTE_WINDOW)
    frame_id = 0
    try:
        while not camera_stop.is_set():
            ok, frame = capture.read()
            if not ok:
                time.sleep(0.15)
                continue
            frame_id += 1
            plates = []
            if frame_id % FRAME_SKIP == 0:
                plates = reader.recognize_bgr(frame)
                vote_buffer.add(plates)
            stable = vote_buffer.best()
            display_plates = [stable] if stable else plates
            annotated = draw_plates(frame, display_plates or [])
            with camera_lock:
                latest_camera_frame = annotated
                if stable:
                    latest_camera_plates = [stable]
            time.sleep(0.01)
    finally:
        capture.release()


def start_camera_worker(source):
    global camera_thread
    stop_camera_worker()
    camera_stop.clear()
    camera_thread = threading.Thread(
        target=_camera_worker, args=(source,), daemon=True, name="plpr-lite-camera"
    )
    camera_thread.start()


def stop_camera_worker():
    camera_stop.set()
    if camera_thread and camera_thread.is_alive():
        camera_thread.join(timeout=2)


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/health")
async def health():
    return {"status": "ok", "models_loaded": reader is not None}


@app.post("/api/recognize")
async def recognize_upload(file: UploadFile = File(...)):
    import numpy as np

    content = await file.read()
    arr = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        return JSONResponse({"error": "Invalid image file"}, status_code=400)
    plates = reader.recognize_bgr(arr)
    annotated = draw_plates(arr, plates)
    ok, encoded = cv2.imencode(".jpg", annotated)
    return {
        "plates": [plate_to_dict(p) for p in plates],
        "annotated_image_base64": base64.b64encode(encoded.tobytes()).decode("ascii") if ok else None,
    }


def _serialize_event(event):
    payload = dict(event)
    if "plate" in payload:
        payload["plate"] = plate_to_dict(payload["plate"])
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _video_worker(path, frame_skip, out_queue):
    try:
        for event in iter_video_plate_events(reader, path, frame_skip=frame_skip):
            out_queue.put(event)
    except Exception as exc:
        out_queue.put({"type": "error", "message": str(exc)})
    finally:
        out_queue.put(None)


@app.post("/api/recognize/video")
async def recognize_video(
    file: UploadFile = File(...),
    frame_skip: int = Form(default=FRAME_SKIP),
):
    suffix = Path(file.filename or "upload.mp4").suffix or ".mp4"
    temp_path = OUTPUT_DIR / f"upload_{int(time.time())}{suffix}"
    temp_path.write_bytes(await file.read())

    out_queue = queue.Queue()
    worker = threading.Thread(
        target=_video_worker,
        args=(str(temp_path), frame_skip, out_queue),
        daemon=True,
        name="plpr-lite-video-worker",
    )
    worker.start()

    async def event_stream():
        yield _serialize_event({"type": "started"})
        while True:
            event = await asyncio.to_thread(out_queue.get)
            if event is None:
                break
            yield _serialize_event(event)
            await asyncio.sleep(0)

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers=STREAM_HEADERS,
    )


@app.post("/api/camera/start")
async def camera_start(source: str = Form(default="0")):
    start_camera_worker(source)
    return {"started": True, "source": source}


@app.post("/api/camera/stop")
async def camera_stop_route():
    stop_camera_worker()
    return {"stopped": True}


@app.get("/api/camera/latest")
async def camera_latest():
    with camera_lock:
        frame = latest_camera_frame
        plates = list(latest_camera_plates)
    if frame is None:
        return {"plates": [], "image": None}
    ok, encoded = cv2.imencode(".jpg", frame)
    return {
        "plates": [plate_to_dict(p) for p in plates],
        "image_base64": base64.b64encode(encoded.tobytes()).decode("ascii") if ok else None,
    }


def mjpeg_generator():
    while True:
        with camera_lock:
            frame = latest_camera_frame
        if frame is not None:
            ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ok:
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                    + encoded.tobytes()
                    + b"\r\n"
                )
        time.sleep(0.08)


@app.get("/api/stream.mjpg")
async def stream_mjpeg():
    return StreamingResponse(
        mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


def main():
    host = os.getenv("LITE_HOST", "0.0.0.0")
    port = int(os.getenv("LITE_PORT", "8502"))
    uvicorn.run("lite.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
