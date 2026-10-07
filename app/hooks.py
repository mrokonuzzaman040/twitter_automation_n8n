"""Outbound events to n8n. Every event is one JSON POST to the n8n webhook set in Settings."""
import httpx

from . import db

DEFAULT_URL = "http://n8n:5678/webhook/social-agents"


def send(event: str, account=None, data=None):
    """POST the event and return (ok, detail). Raises nothing."""
    url = db.get_setting("n8n_webhook_url", DEFAULT_URL)
    payload = {"event": event, "time": db.now(), "data": data or {},
               "account": {k: account[k] for k in ("id", "handle", "platform", "topic", "timezone")} if account else None}
    try:
        r = httpx.post(url, json=payload, timeout=10)
    except httpx.HTTPError as e:
        return False, f"n8n not reachable at {url}: {str(e)[:150]}"
    if r.status_code == 404:
        return False, "n8n answered 404 - the 'Social Agents - Events' workflow is not active"
    if r.status_code >= 400:
        return False, f"n8n answered HTTP {r.status_code}"
    return True, f"delivered to {url}"


def emit(event: str, account=None, data=None):
    """Send an event if n8n events are switched on; a failure is logged, never raised."""
    if db.get_setting("n8n_events", "1") != "1":
        return
    ok, detail = send(event, account, data)
    if not ok:
        db.log_event(account["id"] if account else None, "n8n", f"Event '{event}' not delivered: {detail}", "warn")
