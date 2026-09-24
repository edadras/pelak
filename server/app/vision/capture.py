"""Threaded frame grabber with automatic reconnect. Always exposes the most recent frame."""
import os
import threading
import time

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;5000000")

import cv2  # noqa: E402


class FrameGrabber:
    def __init__(self, url: str, is_file=False):
        self.url = url
        self.is_file = is_file or (os.path.exists(url) if not url.isdigit() else False)
        self._frame = None
        self._ts = 0.0
        self._seq = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.connected = False
        self.error = ""
        self.fps = 0.0
        self.loops = 0  # times a file source restarted (a scene cut for the tracker)
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"grab-{url[-20:]}")

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def _open(self):
        if self.url.isdigit():
            return cv2.VideoCapture(int(self.url))
        return cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)

    def _run(self):
        backoff = 1.0
        while not self._stop.is_set():
            cap = self._open()
            if not cap.isOpened():
                self.connected = False
                self.error = "اتصال به دوربین برقرار نشد"
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 30)
                continue
            backoff = 1.0
            self.connected, self.error = True, ""
            native_fps = cap.get(cv2.CAP_PROP_FPS) or 25
            if native_fps <= 1 or native_fps > 120:
                native_fps = 25
            count, t0 = 0, time.time()
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    if self.is_file:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop test videos
                        ok, frame = cap.read()
                        self.loops += 1
                    if not ok:
                        self.error = "دریافت تصویر قطع شد"
                        break
                with self._lock:
                    self._frame = frame
                    self._ts = time.time()
                    self._seq += 1
                count += 1
                if time.time() - t0 >= 2:
                    self.fps = count / (time.time() - t0)
                    count, t0 = 0, time.time()
                if self.is_file:
                    time.sleep(1.0 / native_fps)  # play files in real time
            cap.release()
            self.connected = False
            self._stop.wait(1)

    def latest(self):
        """Return (seq, timestamp, frame) of the newest frame (frame may be None)."""
        with self._lock:
            return self._seq, self._ts, self._frame


def grab_one(url: str, timeout=8.0):
    """Open a stream, return the first frame or raise."""
    g = FrameGrabber(url).start()
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            _, _, frame = g.latest()
            if frame is not None:
                return frame
            time.sleep(0.1)
    finally:
        g.stop()
    raise RuntimeError(g.error or "در زمان مقرر تصویری دریافت نشد")
