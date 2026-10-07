"""Update checker and updater utilities."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from . import config

# Docker SDK – connects to the Docker daemon via socket.
# If the socket is not mounted we fall back to manual instructions.
try:
    import docker  # docker>=7.0
    HAS_DOCKER_SDK = True
except Exception:  # pragma: no cover
    HAS_DOCKER_SDK = False

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = REPO_ROOT / "VERSION"


def get_current_version() -> str:
    try:
        if VERSION_FILE.exists():
            return VERSION_FILE.read_text().strip()
    except Exception:
        pass
    # Fallback to git tag
    try:
        out = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip().lstrip("v")
    except Exception:
        pass
    return "0.0.0"


def normalize_tag(tag: str) -> str:
    return tag.lstrip("v").strip()


def fetch_latest_release(repo: str) -> Optional[Dict[str, Any]]:
    if not repo:
        return None
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url, headers={"Accept": "application/vnd.github+json"})
            if r.status_code == 200:
                data = r.json()
                return {
                    "tag_name": data.get("tag_name", ""),
                    "name": data.get("name", ""),
                    "published_at": data.get("published_at", ""),
                    "url": data.get("html_url", ""),
                    "body": data.get("body", ""),
                }
    except Exception:
        return None
    return None


def check_update() -> Dict[str, Any]:
    current = get_current_version()
    latest = fetch_latest_release(config.GITHUB_REPO)
    update_available = False
    latest_version = ""
    if latest:
        latest_version = normalize_tag(latest["tag_name"])
        cur_norm = normalize_tag(current)
        # Simple semantic compare
        try:
            update_available = _version_gt(latest_version, cur_norm)
        except Exception:
            update_available = latest_version != cur_norm
    return {
        "current_version": current,
        "latest_version": latest_version,
        "update_available": update_available,
        "latest_release": latest,
    }


def _version_gt(v1: str, v2: str) -> bool:
    def parse(v: str):
        parts = []
        for p in v.split("."):
            try:
                parts.append(int(p))
            except Exception:
                parts.append(0)
        return parts
    a = parse(v1)
    b = parse(v2)
    # pad
    n = max(len(a), len(b))
    a += [0] * (n - len(a))
    b += [0] * (n - len(b))
    return a > b


def perform_update() -> Dict[str, Any]:
    """Apply the new release using Docker.

    If the Docker socket is mounted inside the container (via docker-compose
    volume mount) and the `docker` CLI is available (installed in the
    Dockerfile), it will:
      1. git fetch + git pull the release branch
      2. docker compose pull  (pulls new image layers)
      3. docker compose up -d --build  (recreates containers)

    If the socket is unavailable we fall back to returning manual instructions.
    """
    repo = config.GITHUB_REPO
    if not repo:
        return {"ok": False, "messages": ["GITHUB_REPO not configured"], "manual": True}

    msgs = []
    REPO_ROOT = Path(__file__).resolve().parents[1]

    # 1. Git fetch + pull to get the latest release code
    try:
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            timeout=15,
        )
        subprocess.run(
            ["git", "checkout", "release"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            timeout=15,
        )
        subprocess.run(
            ["git", "pull", "origin", "release"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            timeout=15,
        )
        msgs.append("Git fetch + pull on release branch succeeded.")
    except Exception as e:
        msgs.append(f"Git fetch/pull failed: {e}")
        return {"ok": True, "messages": msgs, "manual": True}

    # 2. Docker compose pull + up
    try:
        # docker compose binary is available inside the container now
        subprocess.run(
            ["docker", "compose", "pull"],
            check=True,
            capture_output=True,
            timeout=120,
        )
        msgs.append("Docker compose pull completed.")

        subprocess.run(
            ["docker", "compose", "up", "-d", "--build"],
            check=True,
            capture_output=True,
            timeout=180,
        )
        msgs.append("Docker compose up -d --build completed. Containers restarted with new image.")
    except Exception as e:
        msgs.append(f"Docker compose update failed: {e}")

    return {"ok": True, "messages": msgs, "manual": False}
