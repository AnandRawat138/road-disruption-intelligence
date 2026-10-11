"""Server-side secret storage.

Precedence for any secret name (e.g. ``OPENAI_API_KEY``):
  1. Process environment / ``.env`` file (read-only from the UI).
  2. ``runtime/secrets.json`` – written when an operator enters a key in the UI.

``runtime/secrets.json`` is plain JSON protected only by the operating-system
file permissions of the user account running the application. It is NOT
encrypted. It is gitignored and never returned to the browser; the API only
reports whether a secret is set and where it came from.
"""
from __future__ import annotations

import json
import os
import stat
import threading

from .config import settings
from .logging_setup import register_secret

# Secrets the application understands. Anything else is rejected.
KNOWN_SECRETS = {
    "OPENAI_API_KEY": "API key for OpenAI or an OpenAI-compatible provider",
    "ANTHROPIC_API_KEY": "API key for Anthropic",
    "NEWSAPI_KEY": "API key for newsapi.org",
    "GNEWS_API_KEY": "API key for gnews.io",
    "REDDIT_CLIENT_ID": "Reddit OAuth application client id",
    "REDDIT_CLIENT_SECRET": "Reddit OAuth application client secret",
}

_lock = threading.Lock()


def _read_file() -> dict[str, str]:
    path = settings.secrets_file
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if isinstance(v, str)}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_file(data: dict[str, str]) -> None:
    path = settings.secrets_file
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:  # Best effort: owner read/write only (effective on POSIX; limited on Windows).
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    os.replace(tmp, path)


def get_secret(name: str) -> str:
    env_val = os.getenv(name, "").strip()
    if env_val:
        register_secret(env_val)
        return env_val
    with _lock:
        val = _read_file().get(name, "").strip()
    register_secret(val)
    return val


def secret_status(name: str) -> dict:
    """Describe a secret without revealing it."""
    if os.getenv(name, "").strip():
        return {"name": name, "configured": True, "source": "environment", "removable": False}
    with _lock:
        present = bool(_read_file().get(name, "").strip())
    return {"name": name, "configured": present, "source": "local_file" if present else None, "removable": present}


def set_secret(name: str, value: str) -> None:
    if name not in KNOWN_SECRETS:
        raise ValueError(f"Unknown secret name: {name}")
    value = (value or "").strip()
    if not value:
        raise ValueError("Secret value must not be empty")
    if len(value) > 4096 or any(ch in value for ch in "\r\n"):
        raise ValueError("Secret value is malformed")
    register_secret(value)
    with _lock:
        data = _read_file()
        data[name] = value
        _write_file(data)


def delete_secret(name: str) -> bool:
    if name not in KNOWN_SECRETS:
        raise ValueError(f"Unknown secret name: {name}")
    with _lock:
        data = _read_file()
        existed = name in data
        data.pop(name, None)
        _write_file(data)
    return existed


def all_statuses() -> list[dict]:
    out = []
    for name, desc in KNOWN_SECRETS.items():
        st = secret_status(name)
        st["description"] = desc
        out.append(st)
    return out
