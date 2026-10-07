"""Master agent (worker entrypoint): keeps the account list in sync with the master Google Sheet
and makes sure every account that should be running has a live agent."""
import time

from . import config, db, sheets
from .account_agent import AccountAgent

TICK = 3  # seconds


def sync_sheet():
    """Create accounts for new sheet rows and apply edits made in the sheet. Rows are never deleted from here."""
    records = sheets.read_master_accounts()
    targets = sheets.read_target_profiles()
    db.set_setting("sheet_target_profiles", "\n".join(targets))
    auto_start = db.get_setting("auto_start_new", "1") == "1"
    created = updated = 0
    for rec in records:
        try:
            existing = db.find_account(rec["platform"], rec["handle"].lstrip("@"))
            if existing:
                fields = db.normalize_account(rec, partial=True)
                changes = {k: v for k, v in fields.items() if str(existing[k]) != str(v)}
                if changes:
                    db.update_account(existing["id"], **changes)
                    updated += 1
            else:
                account_id = db.create_account(rec, source="sheet", desired_state="running" if auto_start else "stopped")
                db.log_event(account_id, "master", f"Added from sheet: {rec['platform']} @{rec['handle']}")
                created += 1
        except ValueError as e:
            db.log_event(None, "master", f"Sheet row for '{rec.get('handle')}' skipped: {e}", "warn")
    return f"{len(records)} rows, {created} added, {updated} updated" + (f", {len(targets)} target profiles" if targets else "")


def maybe_sync(last_sync):
    if not db.get_setting("master_sheet_id") or not sheets.mode():
        db.set_setting("sync_now", "0")
        return last_sync
    interval = max(1, int(db.get_setting("sheet_sync_minutes", "5") or 5)) * 60
    if db.get_setting("sync_now") != "1" and time.time() - last_sync < interval:
        return last_sync
    db.set_setting("sync_now", "0")
    try:
        result = sync_sheet()
    except Exception as e:
        result = f"failed: {str(e)[:300]}"
        db.log_event(None, "master", f"Sheet sync {result}", "error")
    db.set_setting("sheet_sync_at", db.now())
    db.set_setting("sheet_sync_result", result)
    return time.time()


def main():
    config.require()
    # Nothing is running yet after a (re)start, whatever the database says.
    for a in db.list_accounts(include_deleted=True):
        db.update_account(a["id"], agent_status="stopped", current_task="")
        with db.account(a["id"]) as c:
            c.execute("UPDATE runs SET status='interrupted', finished_at=? WHERE status='running'", (db.now(),))
    db.log_event(None, "master", "Master agent started")

    agents, last_sync, last_trim = {}, 0, 0
    while True:
        try:
            db.set_setting("master_heartbeat", db.now())
            last_sync = maybe_sync(last_sync)
            for a in db.list_accounts(include_deleted=True):
                alive = a["id"] in agents and agents[a["id"]].is_alive()
                if a["deleted"]:
                    if not alive:
                        agents.pop(a["id"], None)
                        db.purge_account(a["id"])
                elif a["desired_state"] in ("running", "paused") and not alive:
                    agents[a["id"]] = AccountAgent(a["id"])
                    agents[a["id"]].start()
            if time.time() - last_trim > 600:
                last_trim = time.time()
                db.trim_events()
                db.trim_llm_calls()
        except Exception as e:
            print(f"[error] master loop: {e!r}", flush=True)
        time.sleep(TICK)


if __name__ == "__main__":
    main()
