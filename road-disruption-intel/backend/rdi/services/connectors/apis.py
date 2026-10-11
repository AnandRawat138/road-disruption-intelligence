"""API-based connectors: GDELT DOC 2.0, NewsAPI.org, GNews.io and Reddit (OAuth)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx

from ...secrets import get_secret
from ..ingest import ArticleIn
from ..text import parse_timestamp
from .base import USER_AGENT, Connector, ConnectorError, FetchResult

DEFAULT_QUERY_TERMS = ['"road closed"', '"traffic diversion"', '"traffic jam"', '"highway blocked"',
                       "waterlogging", "landslide", '"road accident"', '"traffic advisory"']


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class GDELTConnector(Connector):
    type_id = "gdelt_doc"
    display_name = "GDELT DOC 2.0 API"
    description = "Global news index (title + URL, no body). Free, no key."
    access_notes = ("Free public API. GDELT enforces at most one request every 5 seconds per client; HTTP 429 "
                    "responses are reported as RATE_LIMITED. Coverage is a sample of online news.")
    default_config = {"terms": DEFAULT_QUERY_TERMS, "source_country": "india", "timespan": "3d",
                      "request_spacing_seconds": 6, "terms_per_query": 4}
    min_interval_seconds = 6.0

    def fetch(self, limit: int) -> FetchResult:
        res = FetchResult()
        terms = [t for t in self.cfg.get("terms") or [] if t.strip()]
        if not terms:
            raise ConnectorError("NOT_CONFIGURED", "No search terms configured")
        group = max(1, int(self.cfg.get("terms_per_query", 4)))
        groups = [terms[i:i + group] for i in range(0, len(terms), group)]
        client = self._client()
        try:
            for i, g in enumerate(groups):
                if len(res.items) >= limit:
                    break
                if i:
                    self.sleep(max(6.0, float(self.cfg.get("request_spacing_seconds", 6))))
                q = "(" + " OR ".join(g) + ")" if len(g) > 1 else g[0]
                if self.cfg.get("source_country"):
                    q += f" sourcecountry:{self.cfg['source_country']}"
                params = {"query": q, "mode": "artlist", "format": "json", "sort": "datedesc",
                          "maxrecords": min(250, max(1, limit - len(res.items))), "timespan": self.cfg.get("timespan", "3d")}
                try:
                    resp = self._get(client, "https://api.gdeltproject.org/api/v2/doc/doc", params=params)
                    res.requests += 1
                except ConnectorError as e:
                    res.requests += 1
                    res.errors.append(str(e))
                    if e.kind in ("RATE_LIMITED", "AUTH"):
                        res.partial = True
                        break
                    continue
                text = resp.text.strip()
                if not text:
                    continue  # GDELT returns an empty body when nothing matches
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    res.errors.append(f"GDELT returned a non-JSON message: {text[:160]}")
                    continue
                for a in data.get("articles", []) or []:
                    if not isinstance(a, dict) or not a.get("url"):
                        continue
                    res.items.append(ArticleIn(
                        title=a.get("title") or "", url=a.get("url"), source_name=a.get("domain"),
                        source_type="API", connector=self.type_id, language=a.get("language"),
                        published_at=parse_timestamp(a.get("seendate")), retrieved_at=_now(), query_used=q))
        finally:
            if self.client is None:
                client.close()
        return res


class NewsAPIConnector(Connector):
    type_id = "newsapi"
    display_name = "NewsAPI.org"
    description = "Commercial news search API (title, description, truncated content)."
    access_notes = ("Requires NEWSAPI_KEY. The free 'Developer' plan is for development only, has a delay and "
                    "a 100 requests/day limit; production use needs a paid plan.")
    required_secrets = ["NEWSAPI_KEY"]
    default_config = {"query": "(\"road closed\" OR \"traffic diversion\" OR \"traffic jam\" OR waterlogging OR "
                               "landslide OR \"highway blocked\") AND India", "language": "en", "page_size": 50}

    def fetch(self, limit: int) -> FetchResult:
        key = get_secret("NEWSAPI_KEY")
        if not key:
            raise ConnectorError("NOT_CONFIGURED", "NEWSAPI_KEY is not configured")
        res = FetchResult()
        page_size = max(1, min(100, int(self.cfg.get("page_size", 50))))
        client = self._client()
        try:
            page = 1
            while len(res.items) < limit and page <= 5:
                params = {"q": self.cfg.get("query"), "language": self.cfg.get("language", "en"),
                          "sortBy": "publishedAt", "pageSize": page_size, "page": page}
                resp = self._get(client, "https://newsapi.org/v2/everything", params=params,
                                 headers={"X-Api-Key": key})
                res.requests += 1
                try:
                    data = resp.json()
                except ValueError as e:
                    raise ConnectorError("PARSE", "NewsAPI returned invalid JSON") from e
                if data.get("status") != "ok":
                    code = data.get("code", "error")
                    kind = "AUTH" if code in ("apiKeyInvalid", "apiKeyDisabled", "apiKeyMissing") else \
                        "RATE_LIMITED" if code == "rateLimited" else "HTTP"
                    raise ConnectorError(kind, f"NewsAPI error: {code}: {data.get('message', '')[:200]}")
                arts = data.get("articles") or []
                for a in arts:
                    res.items.append(ArticleIn(
                        title=a.get("title") or "", url=a.get("url"), raw_snippet=a.get("description"),
                        summary_text=a.get("description"), body_text=a.get("content"),
                        source_name=(a.get("source") or {}).get("name"), source_type="API", connector=self.type_id,
                        language=self.cfg.get("language", "en"), published_at=parse_timestamp(a.get("publishedAt")),
                        retrieved_at=_now(), query_used=self.cfg.get("query")))
                if len(arts) < page_size or page * page_size >= int(data.get("totalResults") or 0):
                    break
                page += 1
                self.sleep(1.0)
        finally:
            if self.client is None:
                client.close()
        return res


class GNewsConnector(Connector):
    type_id = "gnews"
    display_name = "GNews.io"
    description = "Commercial news search API (title, description, truncated content)."
    access_notes = "Requires GNEWS_API_KEY. Free plan: 100 requests/day, max 10 articles per request."
    required_secrets = ["GNEWS_API_KEY"]
    default_config = {"query": "\"road closed\" OR \"traffic diversion\" OR waterlogging OR landslide",
                      "language": "en", "country": "in"}

    def fetch(self, limit: int) -> FetchResult:
        key = get_secret("GNEWS_API_KEY")
        if not key:
            raise ConnectorError("NOT_CONFIGURED", "GNEWS_API_KEY is not configured")
        res = FetchResult()
        client = self._client()
        try:
            params = {"q": self.cfg.get("query"), "lang": self.cfg.get("language", "en"),
                      "country": self.cfg.get("country", "in"), "max": max(1, min(100, limit)), "apikey": key}
            resp = self._get(client, "https://gnews.io/api/v4/search", params=params)
            res.requests += 1
            try:
                data = resp.json()
            except ValueError as e:
                raise ConnectorError("PARSE", "GNews returned invalid JSON") from e
            if "errors" in data:
                raise ConnectorError("HTTP", f"GNews error: {str(data['errors'])[:200]}")
            for a in data.get("articles") or []:
                res.items.append(ArticleIn(
                    title=a.get("title") or "", url=a.get("url"), raw_snippet=a.get("description"),
                    summary_text=a.get("description"), body_text=a.get("content"),
                    source_name=(a.get("source") or {}).get("name"), source_type="API", connector=self.type_id,
                    language=self.cfg.get("language", "en"), published_at=parse_timestamp(a.get("publishedAt")),
                    retrieved_at=_now(), query_used=self.cfg.get("query")))
        finally:
            if self.client is None:
                client.close()
        return res


class RedditConnector(Connector):
    type_id = "reddit"
    display_name = "Reddit (OAuth API)"
    description = "Public posts from selected subreddits via Reddit's official OAuth API."
    access_notes = ("Unauthenticated access is blocked (HTTP 403 verified). Requires a Reddit 'script' app "
                    "client id/secret and compliance with Reddit's Data API terms. User-generated content: "
                    "always review before acting.")
    required_secrets = ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"]
    default_config = {"subreddits": ["mumbai", "pune", "delhi", "bangalore", "hyderabad", "chennai", "kolkata"],
                      "query": "traffic OR road OR highway OR waterlogging OR diversion", "time": "week"}

    def fetch(self, limit: int) -> FetchResult:
        cid, secret = get_secret("REDDIT_CLIENT_ID"), get_secret("REDDIT_CLIENT_SECRET")
        if not cid or not secret:
            raise ConnectorError("NOT_CONFIGURED", "Reddit OAuth credentials are not configured")
        res = FetchResult()
        client = self._client()
        try:
            try:
                tok = client.post("https://www.reddit.com/api/v1/access_token", data={"grant_type": "client_credentials"},
                                  auth=(cid, secret), headers={"User-Agent": USER_AGENT},
                                  timeout=float(self.source.timeout_seconds or 20))
            except httpx.HTTPError as e:
                raise ConnectorError("NETWORK", f"Reddit token request failed ({type(e).__name__})", True) from e
            res.requests += 1
            if tok.status_code in (401, 403):
                raise ConnectorError("AUTH", "Reddit rejected the client credentials", False, tok.status_code)
            if tok.status_code != 200 or "access_token" not in tok.text:
                raise ConnectorError("HTTP", f"Reddit token request failed (HTTP {tok.status_code})", True, tok.status_code)
            token = tok.json()["access_token"]
            per_sub = max(1, min(25, limit // max(1, len(self.cfg.get("subreddits") or [1]))))
            for i, sub in enumerate(self.cfg.get("subreddits") or []):
                if i:
                    self.sleep(1.0)
                try:
                    resp = self._get(client, f"https://oauth.reddit.com/r/{sub}/search",
                                     params={"q": self.cfg.get("query"), "restrict_sr": 1, "sort": "new",
                                             "t": self.cfg.get("time", "week"), "limit": per_sub},
                                     headers={"Authorization": f"Bearer {token}"})
                    res.requests += 1
                    data = resp.json()
                except (ConnectorError, ValueError) as e:
                    res.errors.append(f"r/{sub}: {e}")
                    continue
                for child in (data.get("data") or {}).get("children", []):
                    p = child.get("data") or {}
                    res.items.append(ArticleIn(
                        title=p.get("title") or "", url=f"https://www.reddit.com{p.get('permalink', '')}",
                        summary_text=(p.get("selftext") or "")[:2000], body_text=p.get("selftext"),
                        source_name=f"Reddit r/{sub}", source_type="SOCIAL", connector=self.type_id,
                        published_at=parse_timestamp(p.get("created_utc")), retrieved_at=_now(),
                        query_used=self.cfg.get("query"), external_id=f"reddit:{p.get('id')}" if p.get("id") else None))
        finally:
            if self.client is None:
                client.close()
        return res
