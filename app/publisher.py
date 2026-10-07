"""Publisher agent: posts due content to X/Twitter and Instagram using the account's own credentials."""
import tempfile
import time
from datetime import datetime, timedelta, timezone

import httpx

from . import config, db, hooks, sheets
from .content import compose

MISSED_AFTER = timedelta(hours=12)
MAX_IMAGE_BYTES = 5 * 1024 * 1024


class PublishError(Exception):
    pass


def _need(creds, platform):
    missing = [k for k in db.CREDENTIAL_FIELDS[platform] if not creds.get(k)]
    if missing:
        raise PublishError(f"Missing {platform} credentials: {', '.join(missing)} - add them in the panel")


def _twitter(account, creds, post) -> str:
    import tweepy
    _need(creds, "twitter")
    keys = (creds["api_key"], creds["api_secret"], creds["access_token"], creds["access_token_secret"])
    media_ids = None
    if post["image_url"]:
        try:
            r = httpx.get(post["image_url"], timeout=30, follow_redirects=True)
            r.raise_for_status()
            if len(r.content) > MAX_IMAGE_BYTES:
                raise PublishError("image larger than 5MB")
            suffix = ".png" if "png" in r.headers.get("content-type", "") else ".jpg"
            with tempfile.NamedTemporaryFile(suffix=suffix) as f:
                f.write(r.content)
                f.flush()
                media = tweepy.API(tweepy.OAuth1UserHandler(*keys)).media_upload(filename=f.name)
            media_ids = [media.media_id]
        except Exception as e:
            db.log_event(account["id"], "publisher", f"Image upload failed, posting text only: {str(e)[:200]}", "warn")
    client = tweepy.Client(consumer_key=keys[0], consumer_secret=keys[1], access_token=keys[2],
                           access_token_secret=keys[3])
    try:
        resp = client.create_tweet(text=compose(post), media_ids=media_ids)
    except tweepy.TweepyException as e:
        raise PublishError(f"X API: {e}")
    return f"https://x.com/{account['handle']}/status/{resp.data['id']}"


def _graph(method, path, token, **params):
    r = httpx.request(method, f"https://graph.facebook.com/{config.GRAPH_API_VERSION}/{path}",
                      data={**params, "access_token": token} if method == "POST" else None,
                      params={**params, "access_token": token} if method == "GET" else None, timeout=60)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code >= 400 or "error" in body:
        raise PublishError(f"Instagram API: {(body.get('error') or {}).get('message') or f'HTTP {r.status_code}'}")
    return body


def _instagram(account, creds, post) -> str:
    _need(creds, "instagram")
    if not post["image_url"]:
        raise PublishError("Instagram posts need an image - set an image URL on this post")
    token, ig = creds["access_token"], creds["ig_user_id"]
    container = _graph("POST", f"{ig}/media", token, image_url=post["image_url"], caption=compose(post))["id"]
    for _ in range(15):
        state = _graph("GET", container, token, fields="status_code").get("status_code")
        if state == "FINISHED":
            break
        if state == "ERROR":
            raise PublishError("Instagram could not process the image (it must be a public JPEG URL)")
        time.sleep(2)
    media_id = _graph("POST", f"{ig}/media_publish", token, creation_id=container)["id"]
    return _graph("GET", media_id, token, fields="permalink").get("permalink", "")


def publish(account, post) -> str:
    creds = db.get_credentials(account["id"])
    return (_twitter if account["platform"] == "twitter" else _instagram)(account, creds, post)


def publish_due(account, ctl):
    """Publish at most one due post per call, so a backlog never goes out as a burst."""
    with db.account(account["id"]) as c:
        due = db.rows(c, "SELECT * FROM posts WHERE status='scheduled' AND scheduled_at <= ? ORDER BY scheduled_at",
                      db.now())
    changed = []
    for post in due:
        ctl.checkpoint()
        age = datetime.now(timezone.utc) - datetime.fromisoformat(post["scheduled_at"])
        if age > MISSED_AFTER:
            update = {"status": "missed", "error": "Slot passed while the agent was not running"}
        else:
            ctl.task(f"Publisher: posting #{post['id']}")
            try:
                url = publish(account, post)
                update = {"status": "posted", "posted_url": url, "posted_at": db.now(), "error": ""}
                db.log_event(account["id"], "publisher", f"Posted #{post['id']} {url}")
                hooks.emit("post_published", account, {"id": post["id"], "text": post["text"], "url": url})
            except Exception as e:
                update = {"status": "failed", "error": str(e)[:500]}
                db.log_event(account["id"], "publisher", f"Post #{post['id']} failed: {str(e)[:300]}", "error")
                hooks.emit("post_failed", account, {"id": post["id"], "text": post["text"], "error": str(e)[:500]})
        with db.account(account["id"]) as c:
            c.execute(f"UPDATE posts SET {','.join(k + '=?' for k in update)} WHERE id=?", (*update.values(), post["id"]))
        changed.append({**post, **update})
        if update["status"] != "missed":
            break
    if changed:
        sheets.safe_upsert(account, changed)
