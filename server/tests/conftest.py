import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="pelak-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ.setdefault("MEDIA_DIR", f"{_tmp}/media")
os.environ.setdefault("SEED_EXAMPLES", "0")
os.environ.pop("REDIS_URL", None)
os.environ["EMBEDDED_WORKER"] = "0"
