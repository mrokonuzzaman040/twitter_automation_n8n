"""Google Sheets: the master accounts sheet (input) and the content schedule sheet (output)."""
import hashlib
import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import db

HEADERS = ["id", "account", "platform", "scheduled_at", "status", "text", "hashtags", "image_url",
           "video_url", "pinterest_source", "posted_url", "updated_at"]
# master sheet column name -> account field
ALIASES = {
    "handle": ["account", "handle", "username", "account name", "account_name", "name"],
    "platform": ["platform", "network"],
    "topic": ["topic", "niche", "account topic", "account_topic"],
    "tone": ["tone", "voice"],
    "language": ["language"],
    "post_times": ["post_times", "post times", "times"],
    "timezone": ["timezone", "time zone", "tz"],
    "cycle_hours": ["cycle_hours", "cycle hours"],
    "post_mode": ["post_mode", "post mode", "mode"],
    "schedule_sheet_id": ["schedule_sheet", "schedule sheet", "schedule_sheet_id"],
}
_client_cache = {}


class SheetsError(Exception):
    pass


def sheet_id(value: str) -> str:
    """Accept either a spreadsheet ID or its full URL."""
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", value or "")
    return m.group(1) if m else (value or "").strip()


def service_account_email() -> str:
    raw = db.get_setting("google_service_account_json")
    try:
        return json.loads(raw).get("client_email", "") if raw else ""
    except json.JSONDecodeError:
        return ""


def _client():
    import gspread
    raw = db.get_setting("google_service_account_json")
    if not raw:
        raise SheetsError("Google service account JSON is not set - add it in Settings")
    key = hashlib.sha256(raw.encode()).hexdigest()
    cached = _client_cache.get(key)
    if cached and time.time() - cached[1] < 1800:
        return cached[0]
    client = gspread.service_account_from_dict(json.loads(raw))
    _client_cache.clear()
    _client_cache[key] = (client, time.time())
    return client


def _platforms(cell: str):
    cell = (cell or "").lower()
    found = []
    if "insta" in cell or re.search(r"\big\b", cell):
        found.append("instagram")
    if "twitter" in cell or re.search(r"\bx\b", cell) or not found:
        found.insert(0, "twitter")
    return found


def read_master_accounts() -> list:
    """Rows of the first tab of the master sheet as account dicts (only columns that are present)."""
    sid = sheet_id(db.get_setting("master_sheet_id"))
    if not sid:
        raise SheetsError("Master accounts sheet is not set - add it in Settings")
    values = _client().open_by_key(sid).sheet1.get_all_values()
    if not values:
        return []
    header = [h.strip().lower() for h in values[0]]
    cols = {field: header.index(a) for field, names in ALIASES.items() for a in names if a in header}
    if "handle" not in cols or "topic" not in cols:
        raise SheetsError("Master sheet needs at least 'account' and 'topic' columns in row 1")
    out = []
    for row in values[1:]:
        rec = {f: row[i].strip() for f, i in cols.items() if i < len(row) and row[i].strip()}
        if not rec.get("handle") or not rec.get("topic"):
            continue
        for platform in _platforms(rec.get("platform", "")):
            out.append({**rec, "platform": platform})
    return out


def _schedule_ws(account):
    import gspread
    sid = sheet_id(account["schedule_sheet_id"] or db.get_setting("schedule_sheet_id"))
    if not sid or not db.get_setting("google_service_account_json"):
        return None
    sh = _client().open_by_key(sid)
    title = f"{account['platform']}-{account['handle']}"[:90]
    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=200, cols=len(HEADERS))
        ws.append_row(HEADERS, value_input_option="RAW")
        return ws


def _row(account, post):
    when = ""
    if post["scheduled_at"]:
        when = datetime.fromisoformat(post["scheduled_at"]).astimezone(ZoneInfo(account["timezone"])).strftime("%Y-%m-%d %H:%M")
    return [f"{account['id']}-{post['id']}", account["handle"], account["platform"], when, post["status"],
            post["text"], post["hashtags"], post["image_url"], post["video_url"], post["media_source_url"],
            post["posted_url"], db.now()]


def upsert_posts(account, posts) -> bool:
    """Write posts to the account's tab in the schedule sheet (update existing rows, append new ones)."""
    ws = _schedule_ws(account)
    if ws is None:
        return False
    keys = ws.col_values(1)
    new = []
    for post in posts:
        row = _row(account, post)
        if row[0] in keys:
            r = keys.index(row[0]) + 1
            ws.update(values=[row], range_name=f"A{r}:L{r}", value_input_option="RAW")
        else:
            new.append(row)
    if new:
        ws.append_rows(new, value_input_option="RAW")
    return True


def safe_upsert(account, posts):
    """upsert_posts that never raises - the sheet is a mirror, the account database is the source of truth."""
    try:
        return upsert_posts(account, posts)
    except Exception as e:
        db.log_event(account["id"], "scheduler", f"Could not update schedule sheet: {str(e)[:300]}", "warn")
        return False
