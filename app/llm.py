"""LLM access. Any OpenAI-compatible chat-completions endpoint works; NVIDIA is the default.

To add a provider, add a preset below (or pick "custom" in Settings and enter its base URL).
"""
import json
import re
import threading
import time

import httpx

from . import config, db

PRESETS = {
    "nvidia": {"base_url": "https://integrate.api.nvidia.com/v1", "model": "meta/llama-3.3-70b-instruct"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "meta-llama/llama-3.3-70b-instruct"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile"},
    "custom": {"base_url": "", "model": ""},
}

# What a model costs, shown next to its name in Settings. For every provider except OpenRouter this is a
# general statement about how that provider bills its public API today, not per-model metering - OpenRouter is
# the one provider whose /models response carries real per-model pricing, so its label is computed from that
# instead of this table. Update this if a provider's billing changes.
PROVIDER_BILLING = {
    "nvidia": "Free (NVIDIA developer tier)",
    "groq": "Free (Groq developer tier)",
    "openai": "Paid",
    "custom": "",
}

_slots = threading.Semaphore(config.LLM_CONCURRENCY)
_models_cache = {}  # (provider, base_url, api_key) -> (time.time(), models, error)
MODELS_CACHE_TTL = 600


class LLMError(Exception):
    pass


def current_config() -> dict:
    provider = db.get_setting("llm_provider", "nvidia")
    preset = PRESETS.get(provider, PRESETS["custom"])
    return {
        "provider": provider,
        "base_url": (db.get_setting("llm_base_url") or preset["base_url"]).rstrip("/"),
        "model": db.get_setting("llm_model") or preset["model"],
        "api_key": db.get_setting("llm_api_key"),
    }


def _price_label(pricing: dict) -> str:
    """OpenRouter-style {"prompt": "0.0000002", "completion": "0.0000002", ...} (dollars per token)."""
    try:
        prompt_price = float(pricing.get("prompt") or 0)
        completion_price = float(pricing.get("completion") or 0)
    except (TypeError, ValueError):
        return ""
    if prompt_price == 0 and completion_price == 0:
        return "Free"
    return f"${prompt_price * 1_000_000:.2f}/1M in, ${completion_price * 1_000_000:.2f}/1M out"


def list_models(provider: str, base_url: str, api_key: str, force: bool = False) -> dict:
    """The provider's model catalog for the Settings dropdown: [{"id", "billing"}], newest cache first.

    Needs the account's own API key (most OpenAI-compatible /models endpoints require it), so this returns
    an explanatory error instead of a list when there is none yet.
    Returns {"models": [...], "error": "", "cached": bool}.
    """
    base_url = (base_url or "").rstrip("/")
    if not api_key:
        return {"models": [], "error": "Save your API key first, then models for this provider load here.", "cached": False}
    if not base_url:
        return {"models": [], "error": "Base URL is not set for this provider.", "cached": False}

    key = (provider, base_url, api_key)
    cached = _models_cache.get(key)
    if cached and not force and time.time() - cached[0] < MODELS_CACHE_TTL:
        return {"models": cached[1], "error": cached[2], "cached": True}

    default_billing = PROVIDER_BILLING.get(provider, "")
    try:
        r = httpx.get(f"{base_url}/models", timeout=20, headers={"Authorization": f"Bearer {api_key}"})
    except httpx.HTTPError as e:
        error = f"Could not reach {base_url}: {e}"
        models = cached[1] if cached else []
    else:
        if r.status_code != 200:
            error = f"{provider} listed no models - HTTP {r.status_code}: {r.text[:200]}"
            models = cached[1] if cached else []
        else:
            try:
                items = r.json().get("data") or []
            except ValueError:
                items = []
            models = []
            for it in items:
                model_id = it.get("id")
                if not model_id:
                    continue
                billing = _price_label(it["pricing"]) if isinstance(it.get("pricing"), dict) else default_billing
                models.append({"id": model_id, "billing": billing})
            models.sort(key=lambda m: m["id"])
            error = "" if models else f"{provider} returned no models"
    _models_cache[key] = (time.time(), models, error)
    return {"models": models, "error": error, "cached": False}


def chat(system: str, user: str, temperature: float = 0.7, max_tokens: int = 3000) -> str:
    cfg = current_config()
    if not cfg["api_key"]:
        raise LLMError("LLM API key is not set - add it in Settings")
    if not cfg["base_url"] or not cfg["model"]:
        raise LLMError("LLM base URL / model is not set - check Settings")
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    last, last_status, last_body, duration_ms = "", 0, "", 0
    for attempt in range(4):
        t0 = time.time()
        try:
            with _slots:
                r = httpx.post(f"{cfg['base_url']}/chat/completions", json=payload, timeout=180,
                               headers={"Authorization": f"Bearer {cfg['api_key']}"})
        except httpx.HTTPError as e:
            last, last_status, last_body = f"network error: {e}", 0, str(e)
        else:
            duration_ms = int((time.time() - t0) * 1000)
            if r.status_code == 200:
                body = r.json()
                usage = body.get("usage") or {}
                db.record_llm_call(cfg["provider"], cfg["model"], ok=True,
                                   prompt_tokens=usage.get("prompt_tokens", 0),
                                   completion_tokens=usage.get("completion_tokens", 0),
                                   total_tokens=usage.get("total_tokens", 0), duration_ms=duration_ms)
                text = body["choices"][0]["message"].get("content") or ""
                return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
            last, last_status, last_body = f"HTTP {r.status_code}: {r.text[:300]}", r.status_code, r.text[:300]
            if r.status_code not in (429, 500, 502, 503, 504):
                break
        time.sleep(4 * 2 ** attempt)
    db.record_llm_call(cfg["provider"], cfg["model"], ok=False, error_kind=_classify_error(last_status, last_body),
                       error=last, duration_ms=duration_ms)
    raise LLMError(f"{cfg['provider']} request failed - {last}")


def _classify_error(status: int, body: str) -> str:
    if status in (400, 404) and "model" in (body or "").lower():
        return "model"
    if status in (401, 403):
        return "auth"
    if status == 429:
        return "rate_limit"
    if status >= 500:
        return "server"
    if status == 0:
        return "network"
    return "other"


def chat_json(system: str, user: str, **kw):
    """Ask for JSON and parse it, tolerating code fences and surrounding prose."""
    text = chat(system + "\nRespond with valid JSON only. No markdown, no commentary.", user, **kw)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if starts:
        try:
            return json.JSONDecoder().raw_decode(text[min(starts):])[0]
        except json.JSONDecodeError:
            pass
    raise LLMError(f"Model did not return valid JSON: {text[:200]}")
