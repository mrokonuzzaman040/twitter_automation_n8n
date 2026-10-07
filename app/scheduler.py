"""Scheduler agent: assigns posts to the account's posting slots and mirrors them to the schedule sheet."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import db, hooks, sheets

MAX_SLOTS = 30


def free_slots(account) -> list:
    """Upcoming posting slots (UTC ISO strings) inside this cycle's window that have no post yet."""
    tz = ZoneInfo(account["timezone"])
    start = datetime.now(tz) + timedelta(minutes=5)
    # A few hours of overlap with the next cycle so no slot falls between two cycles.
    end = start + timedelta(hours=int(account["cycle_hours"]) + 6)
    times = db.parse_times(account["post_times"])
    slots, day = [], start.date()
    while day <= end.date():
        for h, m in times:
            slot = datetime(day.year, day.month, day.day, h, m, tzinfo=tz)
            if start < slot <= end:
                slots.append(slot.astimezone(timezone.utc).isoformat(timespec="seconds"))
        day += timedelta(days=1)
    with db.account(account["id"]) as c:
        taken = {r["scheduled_at"] for r in db.rows(
            c, "SELECT scheduled_at FROM posts WHERE status IN ('draft','scheduled','posted')")}
    return sorted(s for s in slots if s not in taken)[:MAX_SLOTS]


def schedule(account, posts, slots, run_id, ctl) -> int:
    ctl.checkpoint()
    ctl.task("Scheduler: saving schedule")
    status = "draft"  # nothing is published until an admin approves it
    tz = ZoneInfo(account["timezone"])
    ids = []
    with db.account(account["id"]) as c:
        for post, slot in zip(posts, slots):
            cur = c.execute(
                "INSERT INTO posts(run_id, text, hashtags, media_query, image_url, video_url, media_source_url, "
                "source_url, scheduled_at, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, post["text"], post["hashtags"], post["media_query"], post["image_url"], post["video_url"],
                 post["media_source_url"], post["source_url"], slot, status, db.now()))
            ids.append(cur.lastrowid)
        saved = db.rows(c, f"SELECT * FROM posts WHERE id IN ({','.join('?' * len(ids))}) ORDER BY scheduled_at", *ids)
    sheets.safe_upsert(account, saved)
    hooks.emit("drafts_ready", account, {"posts": [
        {**{k: p[k] for k in ("id", "text", "hashtags", "image_url", "scheduled_at")},
         "scheduled_local": datetime.fromisoformat(p["scheduled_at"]).astimezone(tz).strftime("%a %d %b, %H:%M")}
        for p in saved]})
    return len(saved)
