"""Admin panel: JSON API + multi-page UI. Controls agents by writing the desired state the worker obeys."""
import hmac
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware

from . import config, db, hooks, llm, sheets

config.require()
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Social Agents", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=config.session_secret(), same_site="strict", max_age=7 * 86400)


def require_login(request: Request):
    if request.session.get("auth"):
        return
    sent = request.headers.get("authorization", "")
    if config.API_TOKEN and hmac.compare_digest(sent.encode(), f"Bearer {config.API_TOKEN}".encode()):
        return
    raise HTTPException(401, "Login required")


api = APIRouter(prefix="/api", dependencies=[Depends(require_login)])


def bad(e):
    raise HTTPException(400, str(e))


def account_or_404(account_id: int) -> dict:
    a = db.get_account(account_id)
    if not a or a["deleted"]:
        raise HTTPException(404, "Account not found")
    return a


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/approvals")
def approvals():
    return FileResponse(STATIC / "approvals.html")


@app.get("/content")
def content():
    return FileResponse(STATIC / "content.html")


@app.get("/research")
def research():
    return FileResponse(STATIC / "research.html")


@app.get("/logs")
def logs():
    return FileResponse(STATIC / "logs.html")


@app.get("/settings")
def settings():
    return FileResponse(STATIC / "settings.html")


@app.post("/api/login")
def login(request: Request, body: dict = Body(...)):
    if not hmac.compare_digest(str(body.get("password", "")).encode(), config.ADMIN_PASSWORD.encode()):
        time.sleep(1)
        raise HTTPException(401, "Wrong password")
    request.session["auth"] = True
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


# ---------- overview + agent control ----------

@api.get("/overview")
def overview():
    accounts = db.list_accounts()
    for a in accounts:
        with db.account(a["id"]) as c:
            a["counts"] = {r["status"]: r["n"] for r in db.rows(c, "SELECT status, COUNT(*) n FROM posts GROUP BY status")}
            a["has_credentials"] = bool(db.one(c, "SELECT 1 FROM credentials LIMIT 1"))
    beat = db.get_setting("master_heartbeat")
    online = bool(beat) and (datetime.now(timezone.utc) - datetime.fromisoformat(beat)).total_seconds() < 20
    return {
        "accounts": accounts,
        "master": {"online": online, "heartbeat": beat, "sheet_sync_at": db.get_setting("sheet_sync_at"),
                   "sheet_sync_result": db.get_setting("sheet_sync_result"),
                   "llm_ready": bool(db.get_setting("llm_api_key"))},
    }


TRANSITIONS = {"start": "running", "resume": "running", "pause": "paused", "stop": "stopped"}


def apply_action(a: dict, action: str):
    if action == "run_now":
        db.update_account(a["id"], run_now=1, desired_state="running")
    elif action == "pause":
        if a["desired_state"] == "running":
            db.update_account(a["id"], desired_state="paused")
    elif action == "resume":
        if a["desired_state"] == "paused":
            db.update_account(a["id"], desired_state="running")
    elif action in TRANSITIONS:
        db.update_account(a["id"], desired_state=TRANSITIONS[action])
    else:
        bad(f"Unknown action '{action}'")


@api.post("/accounts/{account_id}/action")
def account_action(account_id: int, body: dict = Body(...)):
    a = account_or_404(account_id)
    apply_action(a, body.get("action", ""))
    db.log_event(account_id, "panel", f"Command: {body.get('action')}")
    return {"ok": True}


@api.post("/master/action")
def master_action(body: dict = Body(...)):
    action = body.get("action", "")
    if action == "sync_sheet":
        db.set_setting("sync_now", "1")
    elif action in ("start_all", "pause_all", "resume_all", "stop_all"):
        for a in db.list_accounts():
            apply_action(a, action.removesuffix("_all"))
        db.log_event(None, "panel", f"Command: {action}")
    else:
        bad(f"Unknown action '{action}'")
    return {"ok": True}


# ---------- accounts ----------

@api.post("/accounts")
def create_account(body: dict = Body(...)):
    try:
        return {"id": db.create_account(body)}
    except ValueError as e:
        bad(e)


@api.put("/accounts/{account_id}")
def edit_account(account_id: int, body: dict = Body(...)):
    a = account_or_404(account_id)
    try:
        fields = db.normalize_account({**{k: a[k] for k in db.ACCOUNT_FIELDS}, **body})
    except ValueError as e:
        bad(e)
    other = db.find_account(fields["platform"], fields["handle"])
    if other and other["id"] != account_id:
        bad("Another account already uses that platform and handle")
    fields["schedule_sheet_id"] = str(body.get("schedule_sheet_id", a["schedule_sheet_id"]) or "").strip()
    fields["tone"] = str(body.get("tone", a["tone"]) or "").strip()
    if not str(body.get("target_profiles", "x")).strip():
        fields["target_profiles"] = ""
    db.update_account(account_id, **fields)
    return {"ok": True}


@api.delete("/accounts/{account_id}")
def delete_account(account_id: int):
    account_or_404(account_id)
    # The worker stops the agent, then removes the account row and its database.
    db.update_account(account_id, deleted=1, desired_state="stopped")
    return {"ok": True}


@api.get("/accounts/{account_id}/credentials")
def get_credentials(account_id: int):
    a = account_or_404(account_id)
    saved = db.get_credentials(account_id)
    return {"fields": [{"key": k, "set": bool(saved.get(k)), "hint": ("…" + saved[k][-4:]) if saved.get(k) else ""}
                       for k in db.CREDENTIAL_FIELDS[a["platform"]]]}


@api.put("/accounts/{account_id}/credentials")
def put_credentials(account_id: int, body: dict = Body(...)):
    a = account_or_404(account_id)
    if body.get("clear"):
        db.clear_credentials(account_id)
    else:
        allowed = db.CREDENTIAL_FIELDS[a["platform"]]
        db.set_credentials(account_id, {k: v for k, v in body.items() if k in allowed and str(v).strip()})
    db.log_event(account_id, "panel", "Credentials updated")
    return {"ok": True}


# ---------- content, research, logs ----------

@api.get("/accounts/{account_id}/posts")
def list_posts(account_id: int, status: str = ""):
    account_or_404(account_id)
    with db.account(account_id) as c:
        if status:
            return db.rows(c, "SELECT * FROM posts WHERE status=? ORDER BY scheduled_at DESC LIMIT 300", status)
        return db.rows(c, "SELECT * FROM posts ORDER BY scheduled_at DESC LIMIT 300")


@api.patch("/accounts/{account_id}/posts/{post_id}")
def edit_post(account_id: int, post_id: int, body: dict = Body(...)):
    a = account_or_404(account_id)
    with db.account(account_id) as c:
        post = db.one(c, "SELECT * FROM posts WHERE id=?", post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    if post["status"] == "posted":
        bad("This post is already published")
    update = {k: str(body[k]).strip() for k in ("text", "hashtags", "image_url", "video_url") if k in body}
    if "text" in update and not update["text"]:
        bad("Post text cannot be empty")
    if body.get("scheduled_at"):
        try:
            update["scheduled_at"] = db.to_utc_iso(body["scheduled_at"])
        except ValueError:
            bad("Bad scheduled_at")
    action = body.get("action")
    if action == "retry":
        action = "post_now"
    if action in ("approve", "post_now"):
        update.update(status="scheduled", error="")
        # "Post now", or an approval that comes after the slot time, publishes on the publisher's next run.
        if action == "post_now" or (update.get("scheduled_at") or post["scheduled_at"] or "") < db.now():
            update["scheduled_at"] = db.now()
    elif action == "draft":
        update["status"] = "draft"
    elif action == "reject":
        update["status"] = "rejected"
    elif action:
        bad(f"Unknown action '{action}'")
    if update:
        with db.account(account_id) as c:
            c.execute(f"UPDATE posts SET {','.join(k + '=?' for k in update)} WHERE id=?", (*update.values(), post_id))
        sheets.safe_upsert(a, [{**post, **update}])
    if action:
        db.log_event(account_id, "approval", f"Post #{post_id}: {action} -> {update.get('status', post['status'])}")
    return {"ok": True, "status": update.get("status", post["status"]),
            "scheduled_at": update.get("scheduled_at", post["scheduled_at"]), "agent_running": a["desired_state"] == "running"}


@api.get("/drafts")
def drafts():
    """Every post waiting for approval, across all accounts."""
    out = []
    for a in db.list_accounts():
        with db.account(a["id"]) as c:
            out += [{**p, "account_id": a["id"], "handle": a["handle"], "platform": a["platform"]}
                    for p in db.rows(c, "SELECT * FROM posts WHERE status='draft'")]
    return sorted(out, key=lambda p: p["scheduled_at"] or "")


@api.get("/accounts/{account_id}/research")
def get_research(account_id: int):
    account_or_404(account_id)
    with db.account(account_id) as c:
        brief = db.one(c, "SELECT * FROM briefs ORDER BY id DESC LIMIT 1")
        items = db.rows(c, "SELECT * FROM research WHERE run_id=? ORDER BY category, score DESC, id",
                        brief["run_id"]) if brief else []
        runs = db.rows(c, "SELECT * FROM runs ORDER BY id DESC LIMIT 20")
    if brief:
        brief["brief"] = json.loads(brief["brief"])
    return {"brief": brief, "items": items, "runs": runs}


@api.get("/events")
def events(account_id: int = 0, limit: int = 200):
    limit = max(1, min(1000, limit))
    with db.control() as c:
        if account_id:
            return db.rows(c, "SELECT * FROM events WHERE account_id=? ORDER BY id DESC LIMIT ?", account_id, limit)
        return db.rows(c, "SELECT e.*, a.handle FROM events e LEFT JOIN accounts a ON a.id=e.account_id "
                          "ORDER BY e.id DESC LIMIT ?", limit)


# ---------- settings ----------

PLAIN_SETTINGS = ["llm_provider", "llm_base_url", "llm_model", "master_sheet_id", "schedule_sheet_id",
                  "sheet_sync_minutes", "auto_start_new", "n8n_webhook_url", "n8n_events"]


@api.get("/settings")
def get_settings():
    out = {k: db.get_setting(k) for k in PLAIN_SETTINGS}
    out["llm_provider"] = out["llm_provider"] or "nvidia"
    out["sheet_sync_minutes"] = out["sheet_sync_minutes"] or "5"
    out["auto_start_new"] = out["auto_start_new"] or "1"
    out["n8n_webhook_url"] = out["n8n_webhook_url"] or hooks.DEFAULT_URL
    out["n8n_events"] = out["n8n_events"] or "1"
    out["api_token_set"] = bool(config.API_TOKEN)
    out["llm_api_key_set"] = bool(db.get_setting("llm_api_key"))
    out["google_service_account_email"] = sheets.service_account_email()
    out["presets"] = llm.PRESETS
    out["effective"] = {k: v for k, v in llm.current_config().items() if k != "api_key"}
    return out


@api.put("/settings")
def put_settings(body: dict = Body(...)):
    if body.get("google_service_account_json"):
        try:
            sa = json.loads(body["google_service_account_json"])
            assert sa.get("client_email") and sa.get("private_key")
        except Exception:
            bad("That is not a Google service account key file (JSON with client_email and private_key)")
    for k in PLAIN_SETTINGS:
        if k in body:
            db.set_setting(k, str(body[k]).strip())
    for k in db.SECRET_SETTINGS:
        if body.get(k):
            db.set_setting(k, str(body[k]).strip())
    return {"ok": True}


@api.post("/settings/test-llm")
def test_llm():
    try:
        return {"ok": True, "reply": llm.chat("You are a connectivity check.", "Reply with the single word: OK", max_tokens=20)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@api.post("/settings/test-sheets")
def test_sheets():
    try:
        return {"ok": True, "reply": f"Master sheet readable: {len(sheets.read_master_accounts())} account rows"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:400]}


@api.post("/settings/test-n8n")
def test_n8n():
    ok, detail = hooks.send("test", None, {"message": "Test event from the Social Agents panel"})
    return {"ok": ok, "reply": detail, "error": detail}


app.include_router(api)
