"""Connector base class and HTTP helper with bounded retries.

Retry policy: timeouts, network errors, HTTP 429 and 5xx are retried with
exponential backoff and jitter (``Retry-After`` is honoured up to 60 s).
Authentication failures (401/403) and 404s are permanent and never retried.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field

import httpx

from ...db.models import Source
from ..ingest import ArticleIn

log = logging.getLogger(__name__)
USER_AGENT = "AviralRoadDisruptionIntel/1.0 (+local deployment)"


class ConnectorError(Exception):
    def __init__(self, kind: str, message: str, retryable: bool = False, status: int | None = None):
        super().__init__(message)
        self.kind = kind  # AUTH / NOT_FOUND / RATE_LIMITED / TIMEOUT / NETWORK / HTTP / PARSE / NOT_CONFIGURED
        self.retryable = retryable
        self.status = status


@dataclass
class FetchResult:
    items: list[ArticleIn] = field(default_factory=list)
    requests: int = 0
    errors: list[str] = field(default_factory=list)
    partial: bool = False
    notes: list[str] = field(default_factory=list)
    state_updates: dict = field(default_factory=dict)  # persisted into Source.config (e.g. rotation cursor)


def http_get(client: httpx.Client, url: str, *, params: dict | None = None, headers: dict | None = None,
             retries: int = 3, timeout: float = 20.0, label: str = "source", sleep=time.sleep) -> httpx.Response:
    hdrs = {"User-Agent": USER_AGENT}
    hdrs.update(headers or {})
    last: ConnectorError | None = None
    for attempt in range(retries + 1):
        try:
            resp = client.get(url, params=params, headers=hdrs, timeout=timeout, follow_redirects=True)
        except httpx.TimeoutException:
            last = ConnectorError("TIMEOUT", f"{label}: request timed out after {timeout:.0f}s", True)
        except httpx.HTTPError as e:
            last = ConnectorError("NETWORK", f"{label}: network error ({type(e).__name__})", True)
        else:
            code = resp.status_code
            if code < 400:
                return resp
            if code in (401, 403):
                raise ConnectorError("AUTH", f"{label}: access denied (HTTP {code}) – check credentials or access terms",
                                     False, code)
            if code == 404:
                raise ConnectorError("NOT_FOUND", f"{label}: endpoint not found (HTTP 404)", False, code)
            if code == 429:
                last = ConnectorError("RATE_LIMITED", f"{label}: provider rate limit reached (HTTP 429)", True, code)
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit() and attempt < retries:
                    sleep(min(60, int(retry_after)))
                    continue
            elif code >= 500:
                last = ConnectorError("HTTP", f"{label}: provider server error (HTTP {code})", True, code)
            else:
                raise ConnectorError("HTTP", f"{label}: request rejected (HTTP {code})", False, code)
        if attempt < retries:
            sleep(min(30.0, (2 ** attempt) * 1.5 + random.uniform(0, 1)))
    assert last is not None
    raise last


class Connector:
    type_id = "base"
    display_name = "Base"
    description = ""
    access_notes = ""
    required_secrets: list[str] = []
    default_config: dict = {}
    min_interval_seconds = 1.0  # spacing between requests inside one run

    def __init__(self, source: Source, client: httpx.Client | None = None, sleep=time.sleep):
        self.source = source
        self.cfg = {**self.default_config, **(source.config or {})}
        self.client = client
        self.sleep = sleep

    def configuration_status(self) -> tuple[str, str]:
        from ...secrets import get_secret
        missing = [s for s in self.required_secrets if not get_secret(s)]
        if missing:
            return "NOT_CONFIGURED", f"Missing credentials: {', '.join(missing)}"
        return "CONFIGURED", "Ready"

    def fetch(self, limit: int) -> FetchResult:  # pragma: no cover - overridden
        raise NotImplementedError

    def _client(self) -> httpx.Client:
        return self.client or httpx.Client()

    def _get(self, client: httpx.Client, url: str, **kw) -> httpx.Response:
        return http_get(client, url, retries=int(self.source.max_retries or 0),
                        timeout=float(self.source.timeout_seconds or 20), label=self.display_name,
                        sleep=self.sleep, **kw)
