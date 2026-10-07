"""Research agent: gathers fresh material on an account's topic, then has the LLM turn it into a brief."""
import json
import threading
import time
import xml.etree.ElementTree as ET

import httpx

from . import db, llm

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) social-agents/1.0"}
_ddg_slots = threading.Semaphore(2)


def _item(title, summary="", url="", source="", score=0):
    return {"title": (title or "").strip()[:300], "summary": (summary or "").strip()[:500],
            "url": url or "", "source": source or "", "score": int(score or 0)}


def google_news(query, n=8):
    r = httpx.get("https://news.google.com/rss/search", headers=UA, timeout=20, follow_redirects=True,
                  params={"q": f"{query} when:7d", "hl": "en-US", "gl": "US", "ceid": "US:en"})
    r.raise_for_status()
    out = []
    for it in list(ET.fromstring(r.content).iter("item"))[:n]:
        out.append(_item(it.findtext("title"), it.findtext("pubDate"), it.findtext("link"),
                         it.findtext("source") or "Google News"))
    return out


def _ddg(method, query, n, **kw):
    from ddgs import DDGS
    with _ddg_slots:
        try:
            return list(getattr(DDGS(), method)(query, max_results=n, **kw) or [])
        except Exception as e:
            if "No results" in str(e):  # ddgs raises instead of returning an empty list
                return []
            raise
        finally:
            time.sleep(1)  # stay under DuckDuckGo's rate limit


def ddg_text(query, n=6):
    return [_item(r.get("title"), r.get("body"), r.get("href"), "web") for r in _ddg("text", query, n, timelimit="w")]


def ddg_news(query, n=6):
    return [_item(r.get("title"), r.get("body"), r.get("url"), r.get("source") or "news")
            for r in _ddg("news", query, n, timelimit="w")]


def ddg_videos(query, n=6):
    out = []
    for r in _ddg("videos", query, n, timelimit="w"):
        views = (r.get("statistics") or {}).get("viewCount") or 0
        out.append(_item(r.get("title"), r.get("description"), r.get("content"), r.get("publisher") or "video", views))
    return sorted(out, key=lambda x: -x["score"])


def _plan(topic):
    return [
        ("latest_news", "latest news", [
            lambda: google_news(topic),
            lambda: ddg_news(topic)]),
        ("b2b_offers", "recent B2B offers from companies", [
            lambda: google_news(f'{topic} (B2B OR partnership OR deal OR enterprise OR "launches")'),
            lambda: ddg_text(f"{topic} B2B offer partnership announcement")]),
        ("trending_topics", "trending topics", [
            lambda: ddg_text(f"{topic} trends this week"),
            lambda: google_news(f"{topic} trending")]),
        ("viral_posts", "viral posts", [
            lambda: ddg_text(f"{topic} viral post (site:x.com OR site:reddit.com OR site:linkedin.com)"),
            lambda: ddg_text(f"{topic} most shared post this week")]),
        ("viral_content", "viral content", [
            lambda: ddg_videos(topic),
            lambda: ddg_text(f"most viral {topic} video reel this week")]),
    ]


def run(account, ctl, run_id) -> dict:
    """Collect research for the account topic, store it, and return the brief {summary, angles[]}."""
    topic = account["topic"]
    seen, collected = set(), {}
    from . import social  # imported here: social builds on this module's helpers
    for category, label, sources in _plan(topic) + social.plan(account):
        ctl.checkpoint()
        ctl.task(f"Research: {label}")
        items = []
        for fetch in sources:
            try:
                items += fetch()
            except Exception as e:
                db.log_event(account["id"], "research", f"A source for {label} failed: {str(e)[:200]}", "warn")
        items = [i for i in items if i["title"] and not (i["url"] in seen or seen.add(i["url"]))]
        collected[category] = items
        with db.account(account["id"]) as c:
            c.executemany(
                "INSERT INTO research(run_id, category, title, summary, url, source, score, created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                [(run_id, category, i["title"], i["summary"], i["url"], i["source"], i["score"], db.now())
                 for i in items])

    total = sum(len(v) for v in collected.values())
    db.log_event(account["id"], "research", f"Collected {total} items: " +
                 ", ".join(f"{k}={len(v)}" for k, v in collected.items()))
    if total == 0:
        db.log_event(account["id"], "research",
                     "No research sources returned results - content will rely on the model's own knowledge", "warn")

    ctl.checkpoint()
    ctl.task("Research: writing brief")
    lines = []
    for category, items in collected.items():
        if category == "target_profiles":
            # the best posts of every target, not just the first target's
            picked = [i for src in dict.fromkeys(i["source"] for i in items)
                      for i in sorted((x for x in items if x["source"] == src), key=lambda x: -x["score"])[:3]]
        else:
            picked = items[:8]
        for i in picked:
            lines.append(f"[{category}] {i['source']}: {i['title'][:240]} | {i['summary'][:200]} | {i['url']}")
    brief = llm.chat_json(
        "You are a social media research analyst. You turn raw findings into content angles.",
        f"Topic: {topic}\nPlatform: {account['platform']}\n\n"
        "Raw findings (category | source: title or post text | detail | url). "
        "social_trending = top posts on the platform itself. target_profiles = recent posts of profiles this "
        "account wants to learn from, with their engagement.\n"
        + ("\n".join(lines) or "(none found)") +
        "\n\nReturn a JSON object: {\"summary\": \"3-4 sentence overview of what is happening in this topic right now\", "
        "\"target_insights\": \"what the target profiles and top platform posts are doing that earns engagement: "
        "themes, hooks, formats, length. Empty string if there are no such findings\", "
        "\"angles\": [{\"category\": \"latest_news|b2b_offers|trending_topics|viral_posts|viral_content|"
        "social_trending|target_profiles\", "
        "\"title\": \"short angle name\", \"insight\": \"why this would make a strong post and the key fact to use\", "
        "\"url\": \"source url or empty\"}]}\n"
        "Give 8-12 angles, covering every category that has findings. Only use facts present in the findings. "
        "Angles from target_profiles must be inspired by what works for them, never a copy of their posts.",
        temperature=0.4, model=account["llm_model"])
    if not isinstance(brief, dict):
        brief = {"summary": "", "angles": brief if isinstance(brief, list) else []}
    brief.setdefault("summary", "")
    brief["target_insights"] = str(brief.get("target_insights") or "")
    brief["angles"] = [a for a in brief.get("angles") or [] if isinstance(a, dict)]
    with db.account(account["id"]) as c:
        c.execute("INSERT INTO briefs(run_id, brief, created_at) VALUES(?,?,?)", (run_id, json.dumps(brief), db.now()))
    return brief
