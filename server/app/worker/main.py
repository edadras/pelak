"""Vision worker: claims cameras (lease in the database), runs analytics, reports status.

Run as many worker processes / servers as needed (``docker compose up --scale worker=N``).
Each worker handles up to ``WORKER_MAX_CAMERAS`` cameras; cameras are redistributed
automatically when a worker stops (its leases expire).
"""
import logging
import os
import signal
import socket
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from app.config import settings
from app.core.bus import bus
from app.db import IS_SQLITE, init_db, session_scope
from app.models import Alert, Camera, WorkerNode
from app.vision.capture import FrameGrabber
from app.vision.engines import Engines, encode_jpeg
from app.vision.pipeline import CameraProcessor
from app.vision.sources import build_url, mask_url
from app.worker.store import store_observation

log = logging.getLogger("worker")


def camera_dict(cam: Camera):
    return {
        "id": cam.id, "name": cam.name, "vendor": cam.vendor, "host": cam.host, "port": cam.port,
        "username": cam.username, "password": cam.password, "channel": cam.channel, "stream": cam.stream,
        "url": cam.url, "district_id": cam.district_id, "speed_limit": cam.speed_limit,
        "zones": cam.zones or [], "speed_calibration": dict(cam.speed_calibration or {}),
        "analytics": cam.analytics or {}, "config_version": cam.config_version,
    }


class CameraRunner(threading.Thread):
    def __init__(self, cam: dict, engines):
        super().__init__(daemon=True, name=f"cam-{cam['id']}")
        self.cam = cam
        self.engines = engines
        self.stop_flag = threading.Event()
        self.status, self.message, self.fps = "connecting", "", 0.0
        self.grabber = None

    def run(self):
        try:
            url = build_url(self.cam)
        except Exception as exc:
            self.status, self.message = "error", f"آدرس دوربین نامعتبر: {exc}"
            return
        log.info("camera %s -> %s", self.cam["id"], mask_url(url))
        self.grabber = FrameGrabber(url, is_file=self.cam["vendor"] == "file").start()
        proc = CameraProcessor(self.cam, self.engines, store_observation)
        interval = 1.0 / max(settings.process_fps, 0.5)
        stream_interval = 1.0 / max(settings.stream_fps, 0.5)
        last_seq, last_stream, done, t0 = -1, 0.0, 0, time.time()
        loops = 0
        try:
            while not self.stop_flag.is_set():
                start = time.time()
                seq, ts, frame = self.grabber.latest()
                if frame is None or seq == last_seq:
                    self.status = "online" if self.grabber.connected else "offline"
                    self.message = self.grabber.error
                    if frame is None:
                        # keep the preview alive-ish while connecting
                        self.stop_flag.wait(0.2)
                        continue
                    self.stop_flag.wait(0.02)
                    continue
                last_seq = seq
                if self.grabber.loops != loops:  # test video restarted: don't link vehicles across the cut
                    loops = self.grabber.loops
                    proc.close()
                    proc = CameraProcessor(self.cam, self.engines, store_observation)
                try:
                    annotated = proc.process(frame, ts)
                    self.status, self.message = "online", ""
                except Exception as exc:
                    log.exception("processing failed on camera %s", self.cam["id"])
                    self.status, self.message = "error", str(exc)[:300]
                    annotated = frame
                done += 1
                if time.time() - t0 >= 3:
                    self.fps = done / (time.time() - t0)
                    done, t0 = 0, time.time()
                if time.time() - last_stream >= stream_interval:
                    jpeg = encode_jpeg(annotated, 72, settings.stream_width)
                    if jpeg:
                        bus.set_frame(self.cam["id"], jpeg)
                    last_stream = time.time()
                self.stop_flag.wait(max(0.0, interval - (time.time() - start)))
        finally:
            proc.close()
            self.grabber.stop()

    def stop(self):
        self.stop_flag.set()


class Worker:
    def __init__(self):
        self.id = settings.worker_id
        self.capacity = settings.worker_max_cameras
        self.runners: dict[int, CameraRunner] = {}
        self.engines = None
        self.stop_event = threading.Event()

    def _claim(self, db, now):
        lease = now + timedelta(seconds=settings.lease_seconds)
        # renew own leases
        db.query(Camera).filter(Camera.worker_id == self.id).update({Camera.lease_until: lease},
                                                                     synchronize_session=False)
        free = self.capacity - db.query(Camera).filter(Camera.worker_id == self.id,
                                                       Camera.enabled.is_(True)).count()
        if free > 0:
            q = db.query(Camera).filter(
                Camera.enabled.is_(True),
                or_(Camera.worker_id.is_(None), Camera.lease_until.is_(None), Camera.lease_until < now),
            ).order_by(Camera.id).limit(free)
            if not IS_SQLITE:
                q = q.with_for_update(skip_locked=True)
            for cam in q.all():
                cam.worker_id, cam.lease_until = self.id, lease
                log.info("claimed camera %s (%s)", cam.id, cam.name)
        # release disabled cameras
        db.query(Camera).filter(Camera.worker_id == self.id, Camera.enabled.is_(False)).update(
            {Camera.worker_id: None, Camera.lease_until: None, Camera.status: "disabled"},
            synchronize_session=False)
        return {c.id: c for c in db.query(Camera).filter(Camera.worker_id == self.id, Camera.enabled.is_(True))}

    def tick(self):
        now = datetime.now(timezone.utc)
        with session_scope() as db:
            mine = self._claim(db, now)
            # stop runners for cameras no longer ours or whose config changed
            for cam_id, runner in list(self.runners.items()):
                cam = mine.get(cam_id)
                if cam is None or cam.config_version != runner.cam["config_version"] or not runner.is_alive():
                    runner.stop()
                    self.runners.pop(cam_id)
            to_start = [camera_dict(cam) for cam_id, cam in mine.items() if cam_id not in self.runners]
            # status report
            for cam_id, runner in self.runners.items():
                cam = mine[cam_id]
                prev = cam.status
                cam.status, cam.status_message, cam.fps = runner.status, runner.message or "", round(runner.fps, 1)
                if runner.status == "online":
                    cam.last_seen = now
                if prev == "online" and runner.status in ("offline", "error"):
                    db.add(Alert(kind="camera", level="warning", camera_id=cam_id,
                                 title=f"قطع ارتباط دوربین «{cam.name}»", body=runner.message or ""))
                    bus.publish({"type": "camera_status", "data": {"id": cam_id, "status": runner.status}})
            node = db.get(WorkerNode, self.id) or WorkerNode(id=self.id)
            node.host, node.device, node.capacity = socket.gethostname(), settings.device, self.capacity
            node.cameras, node.last_heartbeat = len(self.runners) + len(to_start), now
            try:
                import psutil

                node.cpu, node.memory = psutil.cpu_percent(), psutil.virtual_memory().percent
            except Exception:
                pass
            db.merge(node)
        if to_start:
            if self.engines is None:
                self.engines = Engines.get()  # slow (model loading): done outside the DB transaction
            for cfg in to_start:
                runner = CameraRunner(cfg, self.engines)
                runner.start()
                self.runners[cfg["id"]] = runner

    def run(self):
        log.info("worker %s starting (capacity %s, device %s)", self.id, self.capacity, settings.device)
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("worker tick failed")
            self.stop_event.wait(max(3, settings.lease_seconds // 3))
        self.shutdown()

    def shutdown(self):
        for r in self.runners.values():
            r.stop()
        try:
            with session_scope() as db:
                db.query(Camera).filter(Camera.worker_id == self.id).update(
                    {Camera.worker_id: None, Camera.lease_until: None, Camera.status: "offline"},
                    synchronize_session=False)
                db.query(WorkerNode).filter(WorkerNode.id == self.id).delete()
        except Exception:
            log.exception("worker shutdown cleanup failed")


def start_background_worker():
    w = Worker()
    threading.Thread(target=w.run, daemon=True, name="worker").start()
    return w


def main():
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()
    if not settings.redis_url:
        log.warning("REDIS_URL is not set: live video and real-time events of this worker will not reach the API. "
                    "Use Redis for separate workers, or EMBEDDED_WORKER=1 on a single server.")
    w = Worker()
    signal.signal(signal.SIGTERM, lambda *_: w.stop_event.set())
    signal.signal(signal.SIGINT, lambda *_: w.stop_event.set())
    w.run()


if __name__ == "__main__":
    main()
