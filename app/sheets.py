"""Google Sheets: the master accounts sheet (input) and the content schedule sheet (output).

Two ways to connect, chosen by what is saved in Settings:
  service account - full read/write through the Sheets API (gspread)
  web app         - no Google Cloud setup: the sheet is read through its public link and written
                    through an Apps Script web app deployed on it (google_apps_script/Code.gs)
"""
import csv
import hashlib
import io
import json
import re
import time

import httpx
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
    "schedule_sheet_id": ["schedule_sheet", "schedule sheet", "schedule_sheet_id"],
    "target_profiles": ["target_profiles", "target profiles", "targets", "target accounts", "competitors"],
}
_client_cache = {}

ACCOUNTS_TAB = "Accounts"            # web app mode: optional tab listing accounts (same columns as ALIASES)
TARGETS_TAB = "Target_Profiles"      # web app mode: Username / Profile_URL / Status
SCHEDULE_TAB = "Content_Schedule"    # web app mode: one tab for every account's posts
PUBLISHED_TAB = "My_Published_Posts"
_tabs_cache = {}      # sheet id -> (time, {tab name lower: gid})
_webapp_cache = {}    # web app url -> (time, version)


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


def mode() -> str:
    """'service_account', 'webapp' (public read + Apps Script write) or '' when nothing is configured."""
    if db.get_setting("google_service_account_json"):
        return "service_account"
    if db.get_setting("master_sheet_id") or db.get_setting("google_webapp_url"):
        return "webapp"
    return ""


# ---------- web app mode: public read ----------

def public_tabs(sid: str) -> dict:
    """{tab name: gid} of a sheet shared as 'Anyone with the link'."""
    cached = _tabs_cache.get(sid)
    if cached and time.time() - cached[0] < 120:
        return cached[1]
    r = httpx.get(f"https://docs.google.com/spreadsheets/d/{sid}/htmlview", timeout=25, follow_redirects=True)
    if r.status_code != 200 or "accounts.google.com" in str(r.url):
        raise SheetsError("The sheet is not readable. Share it as 'Anyone with the link - Viewer', "
                          "or connect a service account instead.")
    tabs = dict(re.findall(r'items\.push\(\{name: "([^"]+)".*?gid: "(\d+)"', r.text))
    _tabs_cache[sid] = (time.time(), tabs)
    return tabs


def public_rows(sid: str, tab: str):
    """All rows of one tab, or None if the sheet has no tab with that name (case-insensitive)."""
    gid = {k.lower(): v for k, v in public_tabs(sid).items()}.get(tab.lower())
    if gid is None:
        return None
    r = httpx.get(f"https://docs.google.com/spreadsheets/d/{sid}/export", params={"format": "csv", "gid": gid},
                  timeout=25, follow_redirects=True)
    r.raise_for_status()
    return list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))


def read_target_profiles() -> list:
    """Active rows of the sheet's Target_Profiles tab as profile links/handles (web app mode)."""
    sid = sheet_id(db.get_setting("master_sheet_id"))
    if mode() != "webapp" or not sid:
        return []
    values = public_rows(sid, TARGETS_TAB) or []
    if not values:
        return []
    header = [h.strip().lower() for h in values[0]]
    col = lambda *names: next((header.index(n) for n in names if n in header), None)
    url, user, status = col("profile_url", "url"), col("username", "handle", "account"), col("status")
    out = []
    for row in values[1:]:
        cell = lambda i: row[i].strip() if i is not None and i < len(row) else ""
        if status is not None and cell(status).lower() not in ("active", ""):
            continue
        if cell(url) or cell(user):
            out.append(cell(url) or cell(user))
    return out


# ---------- web app mode: write through the Apps Script web app ----------

def webapp_call(payload: dict) -> dict:
    url = db.get_setting("google_webapp_url")
    if not url:
        raise SheetsError("Apps Script web app URL is not set - add it in Settings")
    # Apps Script answers a POST with a redirect to the result, which has to be fetched with GET.
    r = httpx.post(url, json=payload, timeout=45, follow_redirects=True)
    try:
        return r.json()
    except ValueError:
        raise SheetsError(f"Web app did not answer with JSON (HTTP {r.status_code}). Deploy it with access 'Anyone'.")


def webapp_version() -> int:
    """2 = google_apps_script/Code.gs (creates tabs, updates rows). 1 = an older append/log-only script.
    The probe writes nothing: a script that does not know 'version' answers 'Sheet not found'."""
    url = db.get_setting("google_webapp_url")
    cached = _webapp_cache.get(url)
    if cached and time.time() - cached[0] < 600:
        return cached[1]
    version = int(webapp_call({"action": "version"}).get("version") or 1)
    _webapp_cache[url] = (time.time(), version)
    return version


def webapp_log(action: str, target: str, ref: str, details: str, status: str):
    """One row in the sheet's dated log tab (Log_YYYY-MM-DD), which the web app creates when needed."""
    out = webapp_call({"action": "log", "row": [db.now(), action, target, ref, details[:1500], status]})
    if out.get("error"):
        raise SheetsError(out["error"])


def _webapp_upsert_posts(account, posts) -> bool:
    if not db.get_setting("google_webapp_url"):
        return False
    full = webapp_version() >= 2
    for post in posts:
        row = _row(account, post)
        if full:
            out = webapp_call({"action": "upsert", "sheet": SCHEDULE_TAB, "header": HEADERS, "row": row})
            if out.get("error"):
                raise SheetsError(out["error"])
        if post["status"] == "posted":
            out = webapp_call({"action": "append", "sheet": PUBLISHED_TAB, "row": [
                post.get("posted_at") or db.now(), "@" + account["handle"], post.get("source_url", ""),
                account["topic"], post["text"], "Published", post["posted_url"]]})
            if out.get("error") and not full:
                raise SheetsError(out["error"])
        if not full or post["status"] in ("posted", "failed"):
            webapp_log("SOCIAL_AGENTS_" + post["status"].upper(), "@" + account["handle"], row[0],
                       post["text"] + (" | " + post["posted_url"] if post["posted_url"] else "")
                       + (" | error: " + post["error"] if post.get("error") else ""), post["status"].upper())
    return True


def describe() -> str:
    """Human-readable connection check for the Settings test button. Writes nothing."""
    m = mode()
    if m == "service_account":
        return f"Service account connected: master sheet readable, {len(read_master_accounts())} account rows"
    if m != "webapp":
        raise SheetsError("Nothing is configured yet - add a sheet link and a web app URL (or a service account)")
    sid = sheet_id(db.get_setting("master_sheet_id"))
    parts = []
    if sid:
        tabs = public_tabs(sid)
        accounts = read_master_accounts()
        parts.append(f"sheet readable ({len(tabs)} tabs), {len(accounts)} account rows, "
                     f"{len(read_target_profiles())} active target profiles")
    if db.get_setting("google_webapp_url"):
        v = webapp_version()
        parts.append("web app v2: writes the Content_Schedule tab and logs" if v >= 2 else
                     "web app (basic script): logs every draft/approval/post to the dated log tab; "
                     "install google_apps_script/Code.gs to also get the Content_Schedule tab")
    else:
        parts.append("no web app URL, so nothing is written to the sheet")
    return "; ".join(parts)


def read_master_accounts() -> list:
    """Account rows of the master sheet as account dicts (only columns that are present).
    Service account: the first tab. Web app mode: the 'Accounts' tab, if the sheet has one."""
    sid = sheet_id(db.get_setting("master_sheet_id"))
    if not sid:
        raise SheetsError("Master accounts sheet is not set - add it in Settings")
    if mode() == "service_account":
        values = _client().open_by_key(sid).sheet1.get_all_values()
    else:
        values = public_rows(sid, ACCOUNTS_TAB)
        if values is None:
            return []  # accounts are managed in the panel; the sheet is still used for targets and logging
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
    if mode() == "webapp":
        return _webapp_upsert_posts(account, posts)
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
