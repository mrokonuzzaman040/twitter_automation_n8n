"""Content agent: writes posts from the research brief."""
import json

from . import db, llm

PLATFORM_RULES = {
    "twitter": "X/Twitter post. Body max 220 characters. 1-3 hashtags. No links. Strong first line hook.",
    "instagram": "Instagram caption. 2-5 short lines with a hook first and a call to action last. 6-10 hashtags.",
}
TWITTER_LIMIT = 280


def compose(post) -> str:
    """Final text as published: body plus hashtags."""
    return (post["text"] + ("\n\n" + post["hashtags"] if post["hashtags"] else "")).strip()


def _fit_twitter(text, tags):
    while tags and len(text) + 2 + len(" ".join(tags)) > TWITTER_LIMIT:
        tags.pop()
    room = TWITTER_LIMIT - (2 + len(" ".join(tags)) if tags else 0)
    if len(text) > room:
        text = text[:room - 1].rstrip() + "…"
    return text, tags


def generate(account, brief, count, ctl) -> list:
    ctl.checkpoint()
    ctl.task(f"Content: writing {count} posts")
    with db.account(account["id"]) as c:
        recent = [r["text"] for r in db.rows(c, "SELECT text FROM posts ORDER BY id DESC LIMIT 20")]
    data = llm.chat_json(
        "You are an expert social media copywriter who writes posts that sound human, specific and timely.",
        f"Account: @{account['handle']} on {account['platform']}\nTopic: {account['topic']}\n"
        f"Language: {account['language']}\nTone: {account['tone'] or 'confident, helpful, conversational'}\n"
        f"Format: {PLATFORM_RULES[account['platform']]}\n\n"
        f"Research summary: {brief.get('summary', '')}\n"
        f"What is working on the platform and for target profiles (learn from the style, do not copy): "
        f"{brief.get('target_insights') or 'no data'}\n"
        f"Angles:\n{json.dumps(brief.get('angles', []), ensure_ascii=False)}\n\n"
        f"Already posted recently (do not repeat these ideas):\n{json.dumps(recent, ensure_ascii=False)}\n\n"
        f"Write exactly {count} posts, each on a different angle, mixing the categories. "
        "Do not invent statistics, quotes or offers that are not in the research.\n"
        "Return a JSON array: [{\"text\": \"post body without hashtags\", \"hashtags\": [\"#tag\"], "
        "\"media_query\": \"2-4 word visual search phrase for a matching image\", "
        "\"source_url\": \"url of the angle used, or empty\"}]",
        temperature=0.8, max_tokens=4000)
    if isinstance(data, dict):
        data = data.get("posts") or next((v for v in data.values() if isinstance(v, list)), [])
    posts = []
    for p in data[:count]:
        if not isinstance(p, dict) or not str(p.get("text", "")).strip():
            continue
        text = str(p["text"]).strip()
        tags = p.get("hashtags") or []
        if isinstance(tags, str):
            tags = tags.split()
        tags = ["#" + str(t).strip().lstrip("#").replace(" ", "") for t in tags if str(t).strip()]
        if account["platform"] == "twitter":
            text, tags = _fit_twitter(text, tags)
        posts.append({"text": text, "hashtags": " ".join(tags),
                      "media_query": str(p.get("media_query") or account["topic"])[:100],
                      "source_url": str(p.get("source_url") or "")[:500]})
    if not posts:
        raise llm.LLMError("Model returned no usable posts")
    return posts
