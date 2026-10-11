# Audit report – previous version (v0) and remediation

Audit date: 11 October 2026. Scope: everything in `road-disruption-intel/` and the sibling `data/` folder.

## 1. What existed

| Area | Finding |
|---|---|
| Stack | FastAPI + SQLAlchemy on SQLite (`backend/roaddb.db`); React/Vite/MapLibre single-file UI (`frontend/src/App.tsx`). `docker-compose.yml` described PostgreSQL/PostGIS, Redis and Celery, but the code actually ran SQLite with an in-process thread – the Docker stack was not usable as written (Celery app referenced a missing `REDIS_URL` setting). |
| API | Working: `/api/disruptions/active`, `/api/events/`, `/api/routes`, `/api/admin`. **Empty routers**: `articles`, `analytics`, `roads`. No pagination, filtering, validation or consistent errors. |
| Frontend | One map page + one settings page. The Vite dev proxy pointed to port **8080** while the backend ran on 8000. Stale compiled `App.js`/`vite.config.js` sat next to the `.ts(x)` sources and took precedence in Vite’s resolution order. |
| Ingestion | Background loop running 7 cities × 17 phrases = **119 Google News requests per cycle**, repeated about every minute (aggressive). No source health, retries, backoff or deduplication beyond exact URL. |
| Mock / fabricated data | `NewsAPIProvider` returned two hard-coded `[DEMO]` articles whenever the key was missing or any error occurred. `seed_2026.py` and `seed_user_10.py` **deleted all records** and inserted hand-written events with `certainty=1.0`. 10+ of the 30 events in `roaddb.db` came from these scripts. `run_experiments.py` used a hard-coded “mock ground truth” of 5 items and hard-coded hardware info; result plots were derived from it. |
| Routing | The “disruption-aware” route forced a detour waypoint 0.05° from the disruption – an illustrative path presented as a bypass. Map geometry fallback drew a fabricated diagonal line around a point. |
| LLM | Ollama only, via LangChain, single model, no provider abstraction, failures swallowed (`return None`), no record of model/provider per extraction, an ML-dataset file appended as a side effect. |
| Geocoding | Nominatim without cache or rate limit; OSMnx graph download per location (slow, heavy). Coordinates presented as exact. |
| Security | Admin endpoint allowed setting **any** key; sensitive values masked only in GET; frontend could post secrets; dev server bound to `0.0.0.0`; no auth; no log redaction. |
| Tests | `tests/` was empty. |
| Data folder | See section 3. |

## 2. Search for placeholders / incomplete code (before)

`TODO`/`pass`/empty: `api/articles.py`, `api/analytics.py`, `api/roads.py` (empty routers), `schemas/disruption.py`,
`schemas/evidence.py`, `schemas/road.py`, `services/nlp/multilingual.py` (empty files); `NewsProvider.fetch_news`
abstract `pass`; `temporal.resolve_interval` contained a no-op `pass` for wrapped intervals. Mock data: `newsapi._mock_data`,
seed scripts, `run_experiments.GT`. Disabled feature: Reddit (commented out after HTTP 403).

## 3. Data inspection

| Check | Result |
|---|---|
| Formats | JSONL only (+ the v0 SQLite DB). All 78,415 rows are valid JSON objects; UTF-8 |
| Duplicates | `raw` has 25,035 rows but only 13,691 distinct `article_id`s and 13,487 distinct URLs (same article found by several queries) |
| Text | `article_text` is identical to `description` in **all** rows – the RSS snippet HTML; there is no article body |
| `city` | The *search* city (`National Highway` appears as a city 1,906 times) – not an event location; `state` is always empty |
| Dates | RFC 822 (RSS) and GDELT `YYYYMMDDTHHMMSSZ`; publication dates range 2008–2026 (77 % in 2025–2026); all retrieved on 11 Sep 2026 |
| Weak labels | **No labels** – only `label_source=LLM_weak_label` and a constant `extraction_confidence=0.85` on every row |
| Evaluation splits | Partition of the relevant file (no overlap) with no ground-truth fields |
| Relevance | Earlier keyword rule; includes non-Indian stories (e.g. “Indian Head Highway”, Maryland) |

Consequences: historical records are **headline-only**; previously reported “classified/weak-labelled” totals cannot be
used as classification results; the city field must not be used as the event location.

## 4. Remediation checklist

| # | Item | Status |
|---|---|---|
| 1 | Back up legacy DB before any change (`runtime/backups/roaddb_legacy_original.db`, SHA-256 verified) | Done |
| 2 | Preserve legacy code (left in `backend/app`, seed scripts **disabled** with a guard; README copied to `docs/`) | Done |
| 3 | New backend package `backend/rdi` with explicit schema, versioned initialisation, backups before migration | Done |
| 4 | Idempotent importer for JSONL/JSON/CSV/legacy SQLite with real counts and error CSV | Done, tested |
| 5 | Canonical URL + external id + content hash + same-source title dedup; different publishers not merged | Done, tested |
| 6 | Connectors: Google News RSS, GDELT, NewsAPI, GNews, Reddit OAuth, custom RSS – retries/backoff/jitter, 401/403/404/429/5xx/timeout handling, isolation | Done; Google News verified live; GDELT live attempt = HTTP 429; others mocked |
| 7 | Remove mock fallbacks; no fake records anywhere | Done |
| 8 | Polling: default 3 h, 12 queries/run with 3 s spacing, min interval 30 min, single-instance scheduler lock | Done |
| 9 | LLM provider abstraction (Ollama, OpenAI-compatible, Anthropic), schema-constrained output, validation, retries, failure records | Done; Ollama verified live; OpenAI key on this PC reached the API but account has no credits (HTTP 429); Anthropic mocked |
| 10 | Classification versions with provider/model/prompt, human corrections, review workflow, reclassification | Done, tested |
| 11 | Geocoding: offline gazetteer + cached, rate-limited Nominatim; approximate precision labels; model never supplies coordinates | Done, tested |
| 12 | Incidents: conservative linking, lifecycle, history, conflicts, staleness, merge/detach, alerts | Done, tested |
| 13 | Professional UI: 11 pages, real metrics, map with clustering/filters/evidence, records table with export | Done, verified in browser |
| 14 | Security: localhost bind, token required for remote, server-side secrets, log redaction, upload/path validation, security headers | Done, tested |
| 15 | Windows scripts: setup/start/stop/LLM setup/diagnostics | Done, executed on this PC (incl. fresh copy in a path with spaces) |
| 16 | Automated tests (no network) | 56 tests passing |
| 17 | Removed: OSRM “bypass routing” from the product (it fabricated detours) | Done – not exposed in v1 |

## 5. Issues found and fixed during verification

* Keyword pre-filter missed “NH-48 closed …” (tests) → added highway/closure patterns.
* `classify_article` held the SQLite write lock during the model call, blocking operator actions → fixed, regression test added.
* Graceful shutdown recorded a running job as FAILED → now INTERRUPTED and resumable.
* `start.bat` treated another copy’s server on the same port as “already running” → now verifies ownership.
* Exhausted API credit (HTTP 429 *no credits*) was retried as a rate limit → now a non-retryable `QUOTA` error.
* llama3:8b put clear diversions/closures into OTHER → prompt v1.1 with category definitions; affected records reclassified.
* Mobile layout: hidden navigation toggle, horizontal overflow, map filters crowding the list → fixed.
* Source-health and backup timestamps were sent without a UTC marker and shown 5.5 h off → fixed, regression test.
* Reclassification silently cleared an operator's approval → approval kept when relevance/category are unchanged;
  otherwise cleared with an audit entry; regression test.
* Diagnostics reported Nominatim as HTTP 403 (anonymous User-Agent) → fixed.
