"""Media agent: finds a Pinterest image (and video, when one exists) for each post.

Pinterest has no open search API, so this searches Pinterest through DuckDuckGo image/video search.
"""
from . import db
from .research import _ddg


def find(query: str, used: set) -> dict:
    out = {"image_url": "", "video_url": "", "media_source_url": ""}
    images, pins = [], []
    # Search engines honour "site:" unevenly for images, so try a few phrasings until Pinterest pins show up.
    for phrasing in (f"pinterest {query} pin", f"{query} site:pinterest.com", f"{query} pinterest"):
        found = _ddg("images", phrasing, 30)
        images = images or found
        pins = [i for i in found if "pinimg.com" in (i.get("image") or "") or "pinterest." in (i.get("url") or "")]
        pins = [i for i in pins if (i.get("image") or "") not in used]
        if pins:
            break
    pins.sort(key=lambda i: "pinterest." not in (i.get("url") or ""))  # real pin pages first
    for i in pins or images:
        url = i.get("image") or ""
        if url.startswith("http") and url not in used:
            used.add(url)
            out["image_url"], out["media_source_url"] = url, i.get("url") or ""
            break
    for v in _ddg("videos", f"{query} pinterest", 8):
        url = v.get("content") or ""
        if "pinterest." in url or "pin.it" in url:
            out["video_url"] = url
            break
    return out


def attach(account, posts, ctl):
    with db.account(account["id"]) as c:
        used = {r["image_url"] for r in db.rows(c, "SELECT image_url FROM posts WHERE image_url != ''")}
    for n, post in enumerate(posts, 1):
        ctl.checkpoint()
        ctl.task(f"Media: Pinterest search {n}/{len(posts)}")
        try:
            post.update(find(post["media_query"], used))
        except Exception as e:
            db.log_event(account["id"], "media", f"Pinterest search failed for '{post['media_query']}': {str(e)[:200]}", "warn")
        for k in ("image_url", "video_url", "media_source_url"):
            post.setdefault(k, "")
