"""Storage.

control.db            - account registry, agent state, settings, event log (shared by web + worker)
accounts/account_N.db - one database per account: its credentials, research, posts and runs
"""
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config, crypto

USE_PG = bool(config.DATABASE_URL)
if USE_PG:
    import psycopg2
    from psycopg2.extras import RealDictCursor

SECRET_SETTINGS = {"llm_api_key", "google_service_account_json"}
ACCOUNT_FIELDS = ["platform", "handle", "topic", "tone", "language", "post_times", "timezone",
                  "cycle_hours", "schedule_sheet_id", "target_profiles"]
PLATFORMS = ("twitter", "instagram")
CREDENTIAL_FIELDS = {
    "twitter": ["api_key", "api_secret", "access_token", "access_token_secret"],
    "instagram": ["ig_user_id", "access_token"],
}

CONTROL_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    handle TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT '',
    tone TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'English',
    post_times TEXT NOT NULL DEFAULT '09:00,13:00,18:00',
    timezone TEXT NOT NULL DEFAULT 'UTC',
    cycle_hours INTEGER NOT NULL DEFAULT 24,
    post_mode TEXT NOT NULL DEFAULT 'approval',
    schedule_sheet_id TEXT NOT NULL DEFAULT '',
    target_profiles TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'panel',
    desired_state TEXT NOT NULL DEFAULT 'stopped',
    agent_status TEXT NOT NULL DEFAULT 'stopped',
    current_task TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    last_cycle_at TEXT,
    next_cycle_at TEXT,
    heartbeat_at TEXT,
    run_now INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    agent TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_account ON events(account_id, id);
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    ok INTEGER NOT NULL,
    error_kind TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS llm_calls_model ON llm_calls(provider, model, id);
"""

CONTROL_SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    platform TEXT NOT NULL,
    handle TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT '',
    tone TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'English',
    post_times TEXT NOT NULL DEFAULT '09:00,13:00,18:00',
    timezone TEXT NOT NULL DEFAULT 'UTC',
    cycle_hours INTEGER NOT NULL DEFAULT 24,
    post_mode TEXT NOT NULL DEFAULT 'approval',
    schedule_sheet_id TEXT NOT NULL DEFAULT '',
    target_profiles TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'panel',
    desired_state TEXT NOT NULL DEFAULT 'stopped',
    agent_status TEXT NOT NULL DEFAULT 'stopped',
    current_task TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    last_cycle_at TEXT,
    next_cycle_at TEXT,
    heartbeat_at TEXT,
    run_now INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    account_id INTEGER,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    agent TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_account ON events(account_id, id);
CREATE TABLE IF NOT EXISTS llm_calls (
    id SERIAL PRIMARY KEY,
    ts TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    ok INTEGER NOT NULL,
    error_kind TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS llm_calls_model ON llm_calls(provider, model, id);
"""

ACCOUNT_SCHEMA = """
CREATE TABLE IF NOT EXISTS credentials (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS research (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS briefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    brief TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    text TEXT NOT NULL,
    hashtags TEXT NOT NULL DEFAULT '',
    media_query TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL DEFAULT '',
    video_url TEXT NOT NULL DEFAULT '',
    media_source_url TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    scheduled_at TEXT,
    status TEXT NOT NULL,
    posted_url TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    posted_at TEXT
);
"""

# Applied to databases created by an earlier version; "duplicate column" means already applied.
CONTROL_MIGRATIONS = ["ALTER TABLE accounts ADD COLUMN target_profiles TEXT NOT NULL DEFAULT ''"]
MAX_TARGETS = 15

_initialised = set()
_init_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def to_utc_iso(value: str) -> str:
    """Normalise any ISO timestamp to the UTC format used for storage (so strings compare correctly)."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _conn(path, schema, migrations=()):
    c = sqlite3.connect(path, timeout=20)
    c.row_factory = sqlite3.Row
    try:
        key = str(path)
        if key not in _initialised:
            with _init_lock:
                c.execute("PRAGMA journal_mode=WAL")
                c.executescript(schema)
                for sql in migrations:
                    try:
                        c.execute(sql)
                    except sqlite3.OperationalError:
                        pass
                _initialised.add(key)
        yield c
        c.commit()
    finally:
        c.close()


@contextmanager
def _pg_conn(schema, migrations=()):
    raw = psycopg2.connect(config.DATABASE_URL)
    raw.cursor_factory = RealDictCursor

    class Wrapper:
        def __init__(self, conn):
            self.conn = conn
        def execute(self, sql, args=()):
            sql2 = sql.replace('?', '%s')
            cur = self.conn.cursor()
            cur.execute(sql2, args)
            return cur
        def commit(self):
            self.conn.commit()
        def close(self):
            self.conn.close()
        def cursor(self):
            return self.conn.cursor()

    c = Wrapper(raw)
    try:
        if "pg_control" not in _initialised:
            with _init_lock:
                if "pg_control" not in _initialised:
                    cur = raw.cursor()
                    for stmt in schema.strip().split(";"):
                        stmt = stmt.strip()
                        if stmt:
                            cur.execute(stmt)
                    for sql in migrations:
                        try:
                            cur.execute(sql)
                        except Exception:
                            pass
                    raw.commit()
                    _initialised.add("pg_control")
        yield c
        c.commit()
    finally:
        c.close()


def control():
    if USE_PG:
        return _pg_conn(CONTROL_SCHEMA_PG, CONTROL_MIGRATIONS)
    return _conn(config.DATA_DIR / "control.db", CONTROL_SCHEMA, CONTROL_MIGRATIONS)


def account_path(account_id: int):
    return config.DATA_DIR / "accounts" / f"account_{int(account_id)}.db"


def account(account_id: int):
    return _conn(account_path(account_id), ACCOUNT_SCHEMA)


def _adapt_sql(sql):
    return sql.replace('?', '%s') if USE_PG else sql

def rows(c, sql, *args):
    sql2 = _adapt_sql(sql)
    return [dict(r) for r in c.execute(sql2, args).fetchall()]


def one(c, sql, *args):
    sql2 = _adapt_sql(sql)
    r = c.execute(sql2, args).fetchone()
    return dict(r) if r else None


# ---------- settings ----------

def get_setting(key: str, default: str = "") -> str:
    with control() as c:
        r = one(c, "SELECT value FROM settings WHERE key=?", key)
    if not r or r["value"] == "":
        return default
    return crypto.decrypt(r["value"]) if key in SECRET_SETTINGS else r["value"]


def set_setting(key: str, value: str):
    value = str(value)
    if key in SECRET_SETTINGS and value:
        value = crypto.encrypt(value)
    with control() as c:
        c.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


# ---------- accounts ----------

def normalize_account(data: dict, partial: bool = False) -> dict:
    """Validate and clean user/sheet supplied account fields. Raises ValueError with a readable message."""
    out = {}
    for k in ACCOUNT_FIELDS:
        if k in data and data[k] is not None and str(data[k]).strip() != "":
            out[k] = str(data[k]).strip()
    if "handle" in out:
        out["handle"] = out["handle"].lstrip("@").strip()
    if not partial:
        if not out.get("handle"):
            raise ValueError("Account handle is required")
        if not out.get("topic"):
            raise ValueError("Topic is required")
        out.setdefault("platform", "twitter")
    if "platform" in out:
        out["platform"] = out["platform"].lower()
        if out["platform"] not in PLATFORMS:
            raise ValueError("Platform must be twitter or instagram")
    if "target_profiles" in out:
        out["target_profiles"] = "\n".join(f"{p}:{h}" for p, h in parse_targets(out["target_profiles"], out.get("platform", "twitter")))
    if "post_times" in out:
        out["post_times"] = ",".join(f"{h:02d}:{m:02d}" for h, m in parse_times(out["post_times"]))
    if "timezone" in out:
        try:
            ZoneInfo(out["timezone"])
        except Exception:
            raise ValueError(f"Unknown timezone '{out['timezone']}' (use e.g. Asia/Dhaka, America/New_York, UTC)")
    if "cycle_hours" in out:
        try:
            out["cycle_hours"] = max(1, min(168, int(float(out["cycle_hours"]))))
        except ValueError:
            raise ValueError("cycle_hours must be a number")
    return out


def parse_targets(value: str, default_platform: str) -> list:
    """Target profiles as [(platform, handle)]. Accepts handles, profile URLs, or 'instagram:handle'; one per line or comma."""
    out, seen = [], set()
    for raw in re.split(r"[,;\n]+", value or ""):
        raw, platform = raw.strip(), default_platform
        prefix = re.match(r"^(twitter|x|instagram|ig)\s*:\s*(?!//)(.+)$", raw, re.I)
        if prefix:
            platform = "instagram" if prefix.group(1).lower() in ("instagram", "ig") else "twitter"
            raw = prefix.group(2)
        elif "instagram.com/" in raw.lower():
            platform = "instagram"
        elif re.search(r"(?:^|[/.])(?:x|twitter)\.com/", raw.lower()):
            platform = "twitter"
        handle = re.sub(r"^(https?://)?(www\.)?[a-z]+\.com/", "", raw, flags=re.I).split("/")[0].split("?")[0].lstrip("@")
        if re.fullmatch(r"[A-Za-z0-9_.]{1,40}", handle) and (platform, handle.lower()) not in seen:
            seen.add((platform, handle.lower()))
            out.append((platform, handle))
    return out[:MAX_TARGETS]


def parse_times(value: str):
    times = []
    for part in str(value).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            h, m = part.split(":")
            h, m = int(h), int(m)
            assert 0 <= h < 24 and 0 <= m < 60
        except Exception:
            raise ValueError(f"Bad post time '{part}' (use 24h HH:MM, comma separated)")
        times.append((h, m))
    if not times:
        raise ValueError("At least one post time is required")
    return sorted(set(times))


def list_accounts(include_deleted: bool = False):
    with control() as c:
        sql = "SELECT * FROM accounts" + ("" if include_deleted else " WHERE deleted=0") + " ORDER BY id"
        return rows(c, sql)


def get_account(account_id: int):
    with control() as c:
        return one(c, "SELECT * FROM accounts WHERE id=?", account_id)


def find_account(platform: str, handle: str):
    with control() as c:
        return one(c, "SELECT * FROM accounts WHERE deleted=0 AND platform=? AND lower(handle)=lower(?)",
                   platform, handle)


def create_account(data: dict, source: str = "panel", desired_state: str = "stopped") -> int:
    data = normalize_account(data)
    if find_account(data["platform"], data["handle"]):
        raise ValueError(f"{data['platform']} account @{data['handle']} already exists")
    cols = list(data) + ["source", "desired_state", "created_at"]
    vals = list(data.values()) + [source, desired_state, now()]
    with control() as c:
        if USE_PG:
            sql = f"INSERT INTO accounts({','.join(cols)}) VALUES({','.join('%s' * len(cols))}) RETURNING id"
        else:
            sql = f"INSERT INTO accounts({','.join(cols)}) VALUES({','.join('?' * len(cols))})"
        cur = c.execute(sql, vals)
        if USE_PG:
            row = cur.fetchone()
            account_id = row['id'] if row else None
        else:
            account_id = cur.lastrowid
    with account(account_id):
        pass  # creates the per-account database
    return account_id


def update_account(account_id: int, **fields):
    if not fields:
        return
    sets = ",".join(f"{k}=?" for k in fields)
    with control() as c:
        c.execute(f"UPDATE accounts SET {sets} WHERE id=?", (*fields.values(), account_id))


def purge_account(account_id: int):
    """Remove a deleted account's row and its database files."""
    with control() as c:
        c.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        c.execute("DELETE FROM events WHERE account_id=?", (account_id,))
    p = account_path(account_id)
    _initialised.discard(str(p))
    for suffix in ("", "-wal", "-shm"):
        f = p.with_name(p.name + suffix)
        if f.exists():
            f.unlink()


# ---------- per-account credentials ----------

def get_credentials(account_id: int) -> dict:
    with account(account_id) as c:
        return {r["key"]: crypto.decrypt(r["value"]) for r in rows(c, "SELECT key, value FROM credentials")}


def set_credentials(account_id: int, values: dict):
    with account(account_id) as c:
        for k, v in values.items():
            c.execute("INSERT INTO credentials(key, value) VALUES(?, ?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, crypto.encrypt(str(v).strip())))


def clear_credentials(account_id: int):
    with account(account_id) as c:
        c.execute("DELETE FROM credentials")


# ---------- events ----------

def log_event(account_id, agent: str, message: str, level: str = "info"):
    print(f"[{level}] account={account_id} {agent}: {message}", flush=True)
    with control() as c:
        c.execute("INSERT INTO events(account_id, ts, level, agent, message) VALUES(?,?,?,?,?)",
                  (account_id, now(), level, agent, str(message)[:2000]))


def trim_events(keep: int = 5000):
    with control() as c:
        c.execute("DELETE FROM events WHERE id <= (SELECT MAX(id) FROM events) - ?", (keep,))


# ---------- LLM call log (model health + token/time usage) ----------

def record_llm_call(provider: str, model: str, ok: bool, error_kind: str = "", error: str = "",
                    prompt_tokens: int = 0, completion_tokens: int = 0, total_tokens: int = 0, duration_ms: int = 0):
    with control() as c:
        c.execute("INSERT INTO llm_calls(ts, provider, model, ok, error_kind, error, prompt_tokens, "
                  "completion_tokens, total_tokens, duration_ms) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (now(), provider, model, int(ok), error_kind, str(error)[:300],
                   int(prompt_tokens or 0), int(completion_tokens or 0), int(total_tokens or 0), int(duration_ms or 0)))


def trim_llm_calls(keep: int = 2000):
    with control() as c:
        c.execute("DELETE FROM llm_calls WHERE id <= (SELECT MAX(id) FROM llm_calls) - ?", (keep,))


def broken_models(provider: str) -> set:
    """Models whose most recent call for this provider failed because the model itself was rejected
    (unknown/unsupported model), as opposed to a transient auth/rate-limit/network/server error."""
    with control() as c:
        latest = rows(c, """
            SELECT l.model, l.ok, l.error_kind FROM llm_calls l
            JOIN (SELECT model, MAX(id) AS max_id FROM llm_calls WHERE provider=? GROUP BY model) m
              ON l.model = m.model AND l.id = m.max_id
            WHERE l.provider=?""", provider, provider)
    return {r["model"] for r in latest if not r["ok"] and r["error_kind"] == "model"}


def llm_usage_summary(recent_limit: int = 20) -> dict:
    """Today's call/token/latency totals plus the most recent calls, for the Settings page."""
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    with control() as c:
        recent = rows(c, "SELECT * FROM llm_calls ORDER BY id DESC LIMIT ?", recent_limit)
        today = one(c, "SELECT COUNT(*) AS calls, COALESCE(SUM(total_tokens),0) AS tokens, "
                       "COALESCE(AVG(duration_ms),0) AS avg_ms, "
                       "COALESCE(SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END),0) AS errors "
                       "FROM llm_calls WHERE ts >= ?", since)
    return {"recent": recent, "today": today or {"calls": 0, "tokens": 0, "avg_ms": 0, "errors": 0}}
