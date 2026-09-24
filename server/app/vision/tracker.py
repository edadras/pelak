"""Lightweight multi-object tracker (greedy IoU + centre-distance matching), one per camera."""
import itertools
from collections import Counter, deque

from app.vision.geometry import iou


class Track:
    _ids = itertools.count(1)

    def __init__(self, box, label, conf, ts):
        self.id = next(Track._ids)
        self.box = box
        self.labels = Counter({label: conf})
        self.conf = conf
        self.first_ts = ts
        self.last_ts = ts
        self.hits = 1
        self.missed = 0
        self.history = deque(maxlen=400)  # (ts, x, y) bottom-centre in pixels
        self.history.append((ts, *self.bottom_center))
        # attributes collected by the pipeline
        self.plates = []  # list of plate dicts
        self.plate_attempts = 0
        self.colors = Counter()
        self.types = Counter()
        self.loaded = Counter()
        self.speed = None
        self.direction = ""
        self.line_hits = {}
        self.zone_times = {}  # zone name -> first ts inside
        self.stationary_since = None
        self.state_emitted = set()
        self.best = None  # (score, frame_jpeg, crop_jpeg, plate_jpeg)
        self.best_by_plate = {}  # plate text -> evidence tuple, so images always match the reported plate
        self.foreign_reads = 0  # consecutive confident reads disagreeing with the confirmed plate
        self.emitted_passage = False

    @property
    def bottom_center(self):
        x1, y1, x2, y2 = self.box
        return ((x1 + x2) / 2, y2)

    @property
    def label(self):
        return self.labels.most_common(1)[0][0]

    def split(self, ts):
        """Start a fresh identity at the same position (the tracker merged two vehicles)."""
        fresh = Track(self.box, self.label, self.conf, ts)
        fresh.hits = 1
        return fresh

    def update(self, box, label, conf, ts):
        self.box = box
        self.labels[label] += conf
        self.conf = max(self.conf, conf)
        self.last_ts = ts
        self.hits += 1
        self.missed = 0
        self.history.append((ts, *self.bottom_center))

    def displacement(self, seconds):
        """Max distance (px) of the bottom-centre from its current position within the last N seconds."""
        if not self.history:
            return 0.0
        t, x, y = self.history[-1]
        best = 0.0
        for ts, hx, hy in reversed(self.history):
            if t - ts > seconds:
                break
            best = max(best, ((hx - x) ** 2 + (hy - y) ** 2) ** 0.5)
        return best


class Tracker:
    def __init__(self, iou_thr=0.25, max_missed_s=2.0):
        self.iou_thr = iou_thr
        self.max_missed_s = max_missed_s
        self.tracks: dict[int, Track] = {}

    def update(self, detections, ts):
        """detections: list of (box, label, conf). Returns (active_tracks, finished_tracks)."""
        tracks = list(self.tracks.values())
        pairs = []
        for ti, t in enumerate(tracks):
            tw = t.box[2] - t.box[0]
            for di, (box, _, _) in enumerate(detections):
                score = iou(t.box, box)
                if score < self.iou_thr:
                    # fallback: centre distance for fast / low-fps movement
                    cx1, cy1 = (t.box[0] + t.box[2]) / 2, (t.box[1] + t.box[3]) / 2
                    cx2, cy2 = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                    dist = ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5
                    if dist < 0.6 * tw:
                        score = 0.01 + (0.6 * tw - dist) / (0.6 * tw) * 0.2
                    else:
                        continue
                pairs.append((score, ti, di))
        pairs.sort(reverse=True)
        used_t, used_d = set(), set()
        for _score, ti, di in pairs:
            if ti in used_t or di in used_d:
                continue
            used_t.add(ti)
            used_d.add(di)
            box, label, conf = detections[di]
            tracks[ti].update(box, label, conf, ts)

        for di, (box, label, conf) in enumerate(detections):
            if di not in used_d:
                t = Track(box, label, conf, ts)
                self.tracks[t.id] = t

        finished = []
        for ti, t in enumerate(tracks):
            if ti not in used_t:
                t.missed += 1
                if ts - t.last_ts > self.max_missed_s:
                    finished.append(self.tracks.pop(t.id))
        return list(self.tracks.values()), finished

    def flush(self):
        rest = list(self.tracks.values())
        self.tracks.clear()
        return rest
