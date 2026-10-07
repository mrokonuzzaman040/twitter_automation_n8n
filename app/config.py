import hashlib
import hmac
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
MASTER_KEY = os.environ.get("MASTER_KEY", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
LLM_CONCURRENCY = int(os.environ.get("LLM_CONCURRENCY", "3"))
GRAPH_API_VERSION = os.environ.get("GRAPH_API_VERSION", "v23.0")


def require():
    if len(MASTER_KEY) < 16 or not ADMIN_PASSWORD:
        raise SystemExit("MASTER_KEY (16+ chars) and ADMIN_PASSWORD must be set. Run ./setup.sh to create .env")
    (DATA_DIR / "accounts").mkdir(parents=True, exist_ok=True)


def session_secret() -> str:
    return hmac.new(MASTER_KEY.encode(), b"panel-session", hashlib.sha256).hexdigest()
