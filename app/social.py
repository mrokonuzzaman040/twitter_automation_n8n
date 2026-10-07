"""Social platform research: what is performing on the platform for the topic, and what the
account's target profiles are posting.

Each lookup first uses the platform's own API with the account's credentials (real posts with
engagement numbers). If that is not possible it falls back to a public web search of the profile.
"""
import re

from . import db, publisher
from .research import _ddg, _item

STOPWORDS = {"a", "an", "the", "for", "and", "or", "of", "in", "on", "to", "with", "at", "by", "from", "about"}
POSTS_PER_PROFILE = 10


def _complete(creds, platform):
    return all(creds.get(k) for k in db.CREDENTIAL_FIELDS[platform])


# ---------- X / Twitter ----------

def _x_client(creds):
    import tweepy
    return tweepy.Client(consumer_key=creds["api_key"], consumer_secret=creds["api_secret"],
                         access_token=creds["access_token"], access_token_secret=creds["access_token_secret"])


def _x_items(tweets, source, handle=""):
    out = []
    for t in tweets or []:
        m = t.public_metrics or {}
        likes, reposts, replies = m.get("like_count", 0), m.get("retweet_count", 0), m.get("reply_count", 0)
        url = f"https://x.com/{handle or 'i'}/status/{t.id}"
        out.append(_item(t.text, f"{likes} likes · {reposts} reposts · {replies} replies", url, source,
                         likes + reposts + replies))
    return sorted(out, key=lambda i: -i["score"])


def x_profile(handle, creds):
    client = _x_client(creds)
    user = client.get_user(username=handle, user_auth=True)
    if not user.data:
        raise RuntimeError(f"X profile @{handle} not found")
    r = client.get_users_tweets(user.data.id, max_results=POSTS_PER_PROFILE, exclude=["retweets", "replies"],
                                tweet_fields=["public_metrics", "created_at"], user_auth=True)
    return _x_items(r.data, f"@{handle}", handle)


def x_search(topic, language, creds):
    query = f"{topic} -is:retweet -is:reply" + (" lang:en" if language.lower().startswith("en") else "")
    r = _x_client(creds).search_recent_tweets(query=query, max_results=30, sort_order="relevancy",
                                              tweet_fields=["public_metrics"], user_auth=True)
    return _x_items(r.data, "X search")[:12]


# ---------- Instagram ----------

def _ig_items(media, source):
    out = []
    for m in media or []:
        likes, comments = m.get("like_count") or 0, m.get("comments_count") or 0
        kind = (m.get("media_type") or "").replace("_", " ").lower()
        out.append(_item(m.get("caption") or f"({kind} without caption)", f"{likes} likes · {comments} comments · {kind}",
                         m.get("permalink"), source, likes + comments))
    return sorted(out, key=lambda i: -i["score"])


def ig_profile(handle, creds):
    """Business Discovery: works for target profiles that are Business or Creator accounts."""
    fields = (f"business_discovery.username({handle}){{followers_count,media.limit({POSTS_PER_PROFILE})"
              "{caption,like_count,comments_count,permalink,media_type,timestamp}}")
    body = publisher._graph("GET", creds["ig_user_id"], creds["access_token"], fields=fields)
    return _ig_items(body.get("business_discovery", {}).get("media", {}).get("data"), f"@{handle}")


def topic_hashtag(topic):
    words = [w for w in re.findall(r"[a-z0-9]+", topic.lower()) if w not in STOPWORDS]
    return "".join(words[:2])


def ig_hashtag(topic, creds):
    tag = topic_hashtag(topic)
    if not tag:
        return []
    token, ig = creds["access_token"], creds["ig_user_id"]
    found = publisher._graph("GET", "ig_hashtag_search", token, user_id=ig, q=tag).get("data") or []
    if not found:
        return []
    body = publisher._graph("GET", f"{found[0]['id']}/top_media", token, user_id=ig, limit=25,
                            fields="caption,like_count,comments_count,permalink,media_type")
    return _ig_items(body.get("data"), f"#{tag}")[:12]


# ---------- fallback + plan ----------

def web_profile(platform, handle):
    site = "x.com" if platform == "twitter" else "instagram.com"
    results = _ddg("text", f"site:{site}/{handle}", 8, timelimit="m") or _ddg("text", f"site:{site} {handle}", 8)
    return [_item(r.get("title"), r.get("body"), r.get("href"), f"@{handle}") for r in results]


def _target(account, creds, platform, handle):
    """One target profile: platform API when this account has credentials for that platform, else web search."""
    def fetch():
        if platform == account["platform"] and _complete(creds, platform):
            try:
                items = (x_profile if platform == "twitter" else ig_profile)(handle, creds)
                if items:
                    return items
            except Exception as e:
                db.log_event(account["id"], "research",
                             f"{platform} API could not read @{handle} ({str(e)[:160]}) - using web search instead", "warn")
        return web_profile(platform, handle)
    return fetch


def plan(account):
    """Extra research steps for this account, in the same shape research._plan() uses."""
    creds = db.get_credentials(account["id"])
    platform, topic = account["platform"], account["topic"]
    steps = []
    if _complete(creds, platform):
        name = "X" if platform == "twitter" else "Instagram"
        search = (lambda: x_search(topic, account["language"], creds)) if platform == "twitter" \
            else (lambda: ig_hashtag(topic, creds))
        steps.append(("social_trending", f"top posts on {name}", [search]))
    targets = db.parse_targets(account["target_profiles"], platform)
    # profiles listed in the sheet's Target_Profiles tab apply to every account on that platform
    shared = [t for t in db.parse_targets(db.get_setting("sheet_target_profiles"), "twitter") if t[0] == platform]
    targets = list(dict.fromkeys(targets + shared))[:db.MAX_TARGETS]
    if targets:
        steps.append(("target_profiles", f"{len(targets)} target profiles",
                      [_target(account, creds, p, h) for p, h in targets]))
    return steps
