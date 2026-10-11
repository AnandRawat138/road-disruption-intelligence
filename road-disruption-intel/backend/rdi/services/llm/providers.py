"""LLM provider abstraction.

Providers are NOT interchangeable in every respect; each adapter handles its
own message format, structured-output mechanism and error codes:

* ``ollama``            – local inference, JSON-schema constrained output (``format``).
* ``openai_compatible`` – OpenAI or any server implementing ``/chat/completions``
                          (structured output via ``response_format`` where supported).
* ``anthropic``         – Anthropic Messages API, structured output via a forced tool call.

API keys are read server-side only (``rdi.secrets``).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from ...secrets import get_secret

log = logging.getLogger(__name__)


class LLMError(Exception):
    """Provider failure with a machine-readable kind."""

    def __init__(self, kind: str, message: str, retryable: bool = False, status: int | None = None):
        super().__init__(message)
        self.kind = kind  # CONFIG / AUTH / MODEL_NOT_FOUND / RATE_LIMIT / TIMEOUT / UNAVAILABLE / BAD_RESPONSE
        self.retryable = retryable
        self.status = status

    def as_dict(self) -> dict:
        return {"kind": self.kind, "message": str(self), "retryable": self.retryable, "status": self.status}


@dataclass
class LLMResult:
    text: str
    parsed: dict | None
    model: str
    provider: str
    latency_ms: int
    usage: dict = field(default_factory=dict)


def _is_local(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost")


def _http_error(provider: str, resp: httpx.Response) -> LLMError:
    code = resp.status_code
    try:
        body = resp.json()
        detail = body.get("error", body)
        if isinstance(detail, dict):
            detail = detail.get("message") or json.dumps(detail)[:300]
    except Exception:
        detail = resp.text[:300]
    detail = str(detail)[:300]
    if code in (401, 403):
        return LLMError("AUTH", f"{provider}: authentication failed (HTTP {code}). Check the API key. {detail}", False, code)
    if code == 404:
        return LLMError("MODEL_NOT_FOUND", f"{provider}: model or endpoint not found (HTTP 404). {detail}", False, code)
    if code == 429:
        low = detail.lower()
        if any(w in low for w in ("insufficient_quota", "no credits", "quota exceeded", "billing", "credit balance")):
            # Exhausted account quota does not recover by retrying.
            return LLMError("QUOTA", f"{provider}: account quota/credits exhausted (HTTP 429). {detail}", False, code)
        return LLMError("RATE_LIMIT", f"{provider}: rate limited (HTTP 429). {detail}", True, code)
    if code >= 500:
        return LLMError("UNAVAILABLE", f"{provider}: server error (HTTP {code}). {detail}", True, code)
    return LLMError("BAD_REQUEST", f"{provider}: request rejected (HTTP {code}). {detail}", False, code)


class BaseProvider:
    name = "base"
    supports_schema = False

    def __init__(self, cfg: dict, client: httpx.Client | None = None):
        self.cfg = cfg
        self.base_url = (cfg.get("base_url") or "").rstrip("/")
        self.model = cfg.get("model") or ""
        self.temperature = float(cfg.get("temperature", 0.0))
        self.max_tokens = int(cfg.get("max_tokens", 900))
        self.timeout = float(cfg.get("timeout_seconds", 60))
        self._client = client

    def _post(self, url: str, payload: dict, headers: dict) -> httpx.Response:
        client = self._client or httpx.Client(timeout=httpx.Timeout(self.timeout, connect=10))
        try:
            return client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            raise LLMError("TIMEOUT", f"{self.name}: request timed out after {self.timeout:.0f}s", True) from e
        except httpx.ConnectError as e:
            raise LLMError("UNAVAILABLE", f"{self.name}: cannot connect to {self.base_url}", True) from e
        except httpx.HTTPError as e:
            raise LLMError("UNAVAILABLE", f"{self.name}: network error: {type(e).__name__}", True) from e
        finally:
            if self._client is None:
                client.close()

    def _get(self, url: str, headers: dict, timeout: float = 15) -> httpx.Response:
        client = self._client or httpx.Client(timeout=timeout)
        try:
            return client.get(url, headers=headers)
        except httpx.TimeoutException as e:
            raise LLMError("TIMEOUT", f"{self.name}: request timed out", True) from e
        except httpx.ConnectError as e:
            raise LLMError("UNAVAILABLE", f"{self.name}: cannot connect to {self.base_url}", True) from e
        except httpx.HTTPError as e:
            raise LLMError("UNAVAILABLE", f"{self.name}: network error: {type(e).__name__}", True) from e
        finally:
            if self._client is None:
                client.close()

    def validate_config(self) -> None:
        if not self.base_url:
            raise LLMError("CONFIG", f"{self.name}: base URL is not configured")
        if not self.model:
            raise LLMError("CONFIG", f"{self.name}: model name is not configured")

    def list_models(self) -> list[str]:  # pragma: no cover - overridden
        return []

    def generate_json(self, system: str, user: str, schema: dict) -> LLMResult:  # pragma: no cover
        raise NotImplementedError

    def describe(self) -> dict:
        return {"provider": self.name, "base_url": self.base_url, "model": self.model,
                "structured_output": self.supports_schema}


class OllamaProvider(BaseProvider):
    name = "ollama"
    supports_schema = True

    def version(self) -> str:
        resp = self._get(f"{self.base_url}/api/version", {}, timeout=5)
        if resp.status_code != 200:
            raise _http_error(self.name, resp)
        return resp.json().get("version", "unknown")

    def list_models(self) -> list[str]:
        resp = self._get(f"{self.base_url}/api/tags", {})
        if resp.status_code != 200:
            raise _http_error(self.name, resp)
        return sorted(m.get("name") for m in resp.json().get("models", []) if m.get("name"))

    def list_models_detailed(self) -> list[dict]:
        resp = self._get(f"{self.base_url}/api/tags", {})
        if resp.status_code != 200:
            raise _http_error(self.name, resp)
        out = []
        for m in resp.json().get("models", []):
            det = m.get("details") or {}
            out.append({"name": m.get("name"), "size_bytes": m.get("size"),
                        "parameter_size": det.get("parameter_size"), "family": det.get("family"),
                        "embedding_only": "embedding" in (m.get("capabilities") or []) or det.get("family") in ("nomic-bert", "bert")})
        return out

    def generate_json(self, system: str, user: str, schema: dict) -> LLMResult:
        self.validate_config()
        payload = {
            "model": self.model, "stream": False, "format": schema,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": self.temperature, "num_predict": self.max_tokens},
        }
        t0 = time.monotonic()
        resp = self._post(f"{self.base_url}/api/chat", payload, {})
        if resp.status_code == 404:
            raise LLMError("MODEL_NOT_FOUND", f"ollama: model '{self.model}' is not installed. "
                           f"Pull it with: ollama pull {self.model}", False, 404)
        if resp.status_code != 200:
            raise _http_error(self.name, resp)
        try:
            body = resp.json()
            content = body["message"]["content"]
        except (ValueError, KeyError, TypeError) as e:
            raise LLMError("BAD_RESPONSE", "ollama: unexpected response structure", True) from e
        return LLMResult(content, None, body.get("model", self.model), self.name, int((time.monotonic() - t0) * 1000),
                         {"prompt_tokens": body.get("prompt_eval_count"), "completion_tokens": body.get("eval_count")})


class OpenAICompatibleProvider(BaseProvider):
    name = "openai_compatible"
    supports_schema = True

    def _headers(self) -> dict:
        key = get_secret("OPENAI_API_KEY")
        if not key and not _is_local(self.base_url):
            raise LLMError("CONFIG", "openai_compatible: no API key configured (OPENAI_API_KEY)")
        h = {"Content-Type": "application/json"}
        if key:
            h["Authorization"] = f"Bearer {key}"
        return h

    def list_models(self) -> list[str]:
        resp = self._get(f"{self.base_url}/models", self._headers())
        if resp.status_code != 200:
            raise _http_error(self.name, resp)
        data = resp.json().get("data", [])
        return sorted(m.get("id") for m in data if isinstance(m, dict) and m.get("id"))

    def generate_json(self, system: str, user: str, schema: dict) -> LLMResult:
        self.validate_config()
        mode = self.cfg.get("structured_output", "json_schema")
        payload = {
            "model": self.model, "temperature": self.temperature, "max_tokens": self.max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if mode == "json_schema":
            payload["response_format"] = {"type": "json_schema",
                                          "json_schema": {"name": "road_event", "schema": schema, "strict": False}}
        elif mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        t0 = time.monotonic()
        resp = self._post(f"{self.base_url}/chat/completions", payload, self._headers())
        if resp.status_code != 200:
            raise _http_error(self.name, resp)
        try:
            body = resp.json()
            content = body["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise LLMError("BAD_RESPONSE", "openai_compatible: unexpected response structure", True) from e
        return LLMResult(content, None, body.get("model", self.model), self.name, int((time.monotonic() - t0) * 1000),
                         body.get("usage") or {})


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    supports_schema = True
    API_VERSION = "2023-06-01"

    def _headers(self) -> dict:
        key = get_secret("ANTHROPIC_API_KEY")
        if not key:
            raise LLMError("CONFIG", "anthropic: no API key configured (ANTHROPIC_API_KEY)")
        return {"x-api-key": key, "anthropic-version": self.API_VERSION, "content-type": "application/json"}

    def list_models(self) -> list[str]:
        resp = self._get(f"{self.base_url}/v1/models", self._headers())
        if resp.status_code != 200:
            raise _http_error(self.name, resp)
        return sorted(m.get("id") for m in resp.json().get("data", []) if m.get("id"))

    def generate_json(self, system: str, user: str, schema: dict) -> LLMResult:
        self.validate_config()
        payload = {
            "model": self.model, "max_tokens": self.max_tokens, "temperature": self.temperature, "system": system,
            "messages": [{"role": "user", "content": user}],
            "tools": [{"name": "record_road_event", "description": "Record the structured road-disruption analysis.",
                       "input_schema": schema}],
            "tool_choice": {"type": "tool", "name": "record_road_event"},
        }
        t0 = time.monotonic()
        resp = self._post(f"{self.base_url}/v1/messages", payload, self._headers())
        if resp.status_code != 200:
            raise _http_error(self.name, resp)
        try:
            body = resp.json()
            blocks = body.get("content", [])
        except ValueError as e:
            raise LLMError("BAD_RESPONSE", "anthropic: response is not JSON", True) from e
        for b in blocks:
            if b.get("type") == "tool_use" and isinstance(b.get("input"), dict):
                return LLMResult(json.dumps(b["input"]), b["input"], body.get("model", self.model), self.name,
                                 int((time.monotonic() - t0) * 1000), body.get("usage") or {})
        text_blocks = " ".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        return LLMResult(text_blocks, None, body.get("model", self.model), self.name,
                         int((time.monotonic() - t0) * 1000), body.get("usage") or {})


PROVIDERS = {"ollama": OllamaProvider, "openai_compatible": OpenAICompatibleProvider, "anthropic": AnthropicProvider}


def build_provider(name: str, cfg: dict, client: httpx.Client | None = None) -> BaseProvider:
    cls = PROVIDERS.get(name)
    if cls is None:
        raise LLMError("CONFIG", f"Unknown LLM provider '{name}'")
    return cls(cfg, client)
