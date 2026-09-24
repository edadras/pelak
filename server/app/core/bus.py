"""Event + frame bus between vision workers and the API.

With ``REDIS_URL`` set, workers on any number of servers publish to Redis. Without it an
in-process bus is used (single node, ``EMBEDDED_WORKER=1``).
"""
import asyncio
import json
import threading
import time

from app.config import settings

CHANNEL = "pelak:events"
FRAME_TTL = 10


class MemoryBus:
    def __init__(self):
        self._frames = {}
        self._subs = set()
        self._lock = threading.Lock()

    def publish(self, message: dict):
        data = json.dumps(message, ensure_ascii=False, default=str)
        with self._lock:
            subs = list(self._subs)
        for loop, queue in subs:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, data)
            except RuntimeError:
                pass

    def set_frame(self, camera_id, jpeg: bytes):
        self._frames[camera_id] = (time.time(), jpeg)

    def get_frame(self, camera_id):
        item = self._frames.get(camera_id)
        if not item or time.time() - item[0] > FRAME_TTL:
            return None
        return item[1]

    async def subscribe(self):
        queue = asyncio.Queue(maxsize=500)
        entry = (asyncio.get_running_loop(), queue)
        with self._lock:
            self._subs.add(entry)
        try:
            while True:
                yield await queue.get()
        finally:
            with self._lock:
                self._subs.discard(entry)

    async def aget_frame(self, camera_id):
        return self.get_frame(camera_id)


class RedisBus:
    def __init__(self, url):
        import redis
        import redis.asyncio as aredis

        self._r = redis.Redis.from_url(url)
        self._ar = aredis.Redis.from_url(url)

    def publish(self, message: dict):
        self._r.publish(CHANNEL, json.dumps(message, ensure_ascii=False, default=str))

    def set_frame(self, camera_id, jpeg: bytes):
        self._r.set(f"pelak:frame:{camera_id}", jpeg, ex=FRAME_TTL)

    def get_frame(self, camera_id):
        return self._r.get(f"pelak:frame:{camera_id}")

    async def aget_frame(self, camera_id):
        return await self._ar.get(f"pelak:frame:{camera_id}")

    async def subscribe(self):
        pubsub = self._ar.pubsub()
        await pubsub.subscribe(CHANNEL)
        try:
            async for msg in pubsub.listen():
                if msg.get("type") == "message":
                    data = msg["data"]
                    yield data.decode() if isinstance(data, bytes) else data
        finally:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()


bus = RedisBus(settings.redis_url) if settings.redis_url else MemoryBus()
