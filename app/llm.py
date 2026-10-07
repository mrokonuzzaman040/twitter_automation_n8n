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

_slots = threading.Semaphore(config.LLM_CONCURRENCY)


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
    last = ""
    for attempt in range(4):
        try:
            with _slots:
                r = httpx.post(f"{cfg['base_url']}/chat/completions", json=payload, timeout=180,
                               headers={"Authorization": f"Bearer {cfg['api_key']}"})
        except httpx.HTTPError as e:
            last = f"network error: {e}"
        else:
            if r.status_code == 200:
                text = r.json()["choices"][0]["message"].get("content") or ""
                return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
            last = f"HTTP {r.status_code}: {r.text[:300]}"
            if r.status_code not in (429, 500, 502, 503, 504):
                break
        time.sleep(4 * 2 ** attempt)
    raise LLMError(f"{cfg['provider']} request failed - {last}")


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
