"""Structured logging with secret redaction."""
from __future__ import annotations

import json
import logging
import logging.handlers
import re
from datetime import datetime, timezone

from .config import settings

# Patterns that look like credentials. Applied to every log record.
_REDACT_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|apikey|token|secret|password|authorization|x-api-key)(\"?\s*[:=]\s*\"?)([^\s\"&,;]+)"),
    re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._\-]+)"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{8,}"),
]

_known_secrets: set[str] = set()


def register_secret(value: str | None) -> None:
    """Register a literal secret so it is always redacted from logs."""
    if value and len(value) >= 6:
        _known_secrets.add(value)


def redact(text: str) -> str:
    if not text:
        return text
    for s in _known_secrets:
        if s in text:
            text = text.replace(s, "[REDACTED]")
    text = _REDACT_PATTERNS[0].sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
    text = _REDACT_PATTERNS[1].sub(lambda m: f"{m.group(1)}[REDACTED]", text)
    text = _REDACT_PATTERNS[2].sub("[REDACTED]", text)
    text = _REDACT_PATTERNS[3].sub("[REDACTED]", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        red = redact(msg)
        if red != msg:
            record.msg = red
            record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("source_id", "job_id", "article_id", "batch_id", "provider"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    settings.ensure_dirs()
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    redactor = RedactingFilter()

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
    console.addFilter(redactor)

    file_handler = logging.handlers.RotatingFileHandler(
        settings.logs_dir / "backend.jsonl", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(JsonFormatter())
    file_handler.addFilter(redactor)

    root.handlers = [console, file_handler]
    # Quieten noisy libraries; never log request headers.
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True
