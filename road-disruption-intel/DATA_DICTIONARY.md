# Data dictionary

Database: SQLite (`runtime/rdi.db`, WAL mode). All timestamps are stored in **UTC** and displayed in IST.
Schema version is recorded in `schema_version`; upgrades are preceded by an automatic backup.

## Historical source files (`data/`, read-only)

| File | Rows | Role on import | Notes |
|---|---|---|---|
| `raw/raw_articles.jsonl` | 25,035 | `RAW_ARTICLES` | All fetched rows; 13,691 distinct `article_id`s, many repeated across search queries |
| `deduplicated/deduplicated_articles.jsonl` | 25,035 | `DEDUPLICATED` | Same rows + earlier `is_duplicate` / `deduplication_method` flags |
| `relevant/relevant_articles.jsonl` | 8,914 | `PRIOR_RELEVANT` | Earlier keyword rule (`deterministic_lexical_rule_v1`) output |
| `weak_labels/weak_labeled_events.jsonl` | 8,914 | `WEAK_LABEL_FILE` | **Contains no event labels** – only `label_source=LLM_weak_label` and a constant `extraction_confidence=0.85`. Imported as provenance only |
| `evaluation/{dev,val,test}_split.jsonl` | 6,239 / 1,337 / 1,338 | `EVAL_SPLIT` | Partition of the relevant file; no ground-truth labels |
| `validated/` | – | – | Empty folder |
| `backend/roaddb.db` (v0 app) | 1,603 articles | `LEGACY_DB` | Articles imported; its 30 events were **not** imported (several were hand-written by seed scripts) |

Source-file fields: `article_id, source, source_type (RSS/API), source_url, original_url, title, description
(RSS HTML snippet), article_text (identical to description), publication_time (RFC 822 or GDELT
YYYYMMDDTHHMMSSZ), retrieval_time, language, author, query_used, city (the **search city**, not the event
location), state (always empty), country, content_hash`. Google News RSS provides only the headline and
publisher – there is no article body in the historical data.

## `articles` – one row per unique source document

| Field | Description |
|---|---|
| `id` | Stable id: `A` + SHA-256 of the canonical URL (23 hex chars) |
| `canonical_url` | Unique. Lower-cased host, no `www.`, no fragment/tracking parameters (`utm_*`, `oc`, `fbclid`…), sorted query, Google News `/rss/articles/` ≡ `/articles/` |
| `source_url`, `original_url` | URLs exactly as received |
| `title` | HTML-stripped headline |
| `title_norm`, `title_fingerprint` | Normalised title (publisher suffix removed); fingerprint = hash(source + title) for near-duplicate detection (titles of ≥ 6 words) |
| `content_hash` | SHA-256 of normalised title + summary |
| `summary_text` | HTML-stripped description/snippet |
| `body_text` | Full text when the source provides it (NewsAPI/GNews/Reddit) |
| `raw_snippet` | Original snippet/HTML kept for audit |
| `source_name`, `source_type`, `connector` | Publisher; RSS/API/SOCIAL/IMPORT/LEGACY; connector id (`google_news_rss`, `historical_import`…) |
| `language` | ISO code where known |
| `published_at`, `retrieved_at`, `ingested_at`, `updated_at` | Publication, retrieval by the original collector, insertion here, last change |
| `query_used`, `query_city` | Search query and search city that found it (context only) |
| `external_ids` | Source-system ids (e.g. `RAW_…`, `GDELT_…`) |
| `dataset_flags` | Provenance from historical files (e.g. `prior_lexical_score`, `prior_eval_split`, `in_weak_label_file`) |
| `prefilter_label/score/reason` | Keyword pre-filter (`LIKELY_RELEVANT`, `POSSIBLY_RELEVANT`, `UNLIKELY`). **Not a classification** – used only to prioritise |
| `classification_status` | `UNCLASSIFIED`, `QUEUED`, `PROCESSING`, `CLASSIFIED`, `FAILED` (no valid classification yet) |
| `review_status` | `UNREVIEWED`, `PENDING_REVIEW`, `APPROVED`, `REJECTED`, `NOT_REQUIRED` |
| `current_classification_id`, `incident_id` | Links |
| `classification_attempts` | Number of model attempts |

### Deduplication order
1 canonical URL → 2 external id → 3 content hash *from the same source* → 4 same normalised title *from the
same source* within 3 days. Different publishers are never merged; they become evidence of one incident.

## `article_sightings` – provenance
One row each time an article is seen (file, query, fetch run): `origin_type` (FILE/CONNECTOR/LEGACY_DB),
`origin`, `external_id`, `query_used`, `url`, `match_method` (`new`, `canonical_url`, `external_id`,
`content_hash`, `title_fingerprint`), `batch_id`, `seen_at`. “Total source records” on the dashboard counts
these rows.

## `classifications` – append-only versions

| Field | Values / description |
|---|---|
| `version`, `is_current`, `origin` | Version number per article; exactly one current; `MODEL` or `HUMAN` |
| `provider`, `model`, `prompt_version` | e.g. `ollama`, `llama3:8b`, `v1.1` |
| `status` | `VALID`; `INVALID` (output failed validation); `FAILED` (provider error). Only VALID can be current |
| `error`, `raw_output`, `latency_ms`, `input_chars` | Diagnostics; raw model output kept for audit |
| `relevance` | `RELEVANT`, `RELATED` (transport news, no disruption), `IRRELEVANT`, `NEEDS_REVIEW` |
| `category` | `ACCIDENT, CONGESTION, CLOSURE, DIVERSION, FLOODING, LANDSLIDE, PROTEST, CONSTRUCTION, WEATHER, INFRASTRUCTURE, SECURITY_VIP, OTHER, UNKNOWN` |
| `country, state, city, locality` | State/city normalised to a known Indian state/UT and canonical city names (Bombay→Mumbai …) |
| `road_name, highway_number, direction, affected_segment` | Removed by validation if not present in the source text; highways normalised to `NH-48`, `SH-10` |
| `event_start, event_end` | Only when stated; removed if unparseable or > 400 days from publication |
| `time_status` | `ONGOING, UPCOMING, RESOLVED, UNKNOWN` – as reported **at publication**, not now |
| `severity` | `LOW, MODERATE, HIGH, CRITICAL, UNKNOWN` |
| `reported_delay`, `advisory_action`, `summary` | Advisory action is a suggestion only |
| `evidence_excerpt`, `evidence_verified` | Excerpt and whether it was found (near-)verbatim in the source |
| `model_confidence` | `LOW/MEDIUM/HIGH` – model self-assessment, **not calibrated** |
| `validation_status`, `validation_issues`, `missing_fields` | `PASSED`/`WARNINGS`/`FAILED` and notes |
| `needs_review`, `review_reasons` | Why the record was flagged (low confidence, unverified evidence, unresolved/state-only/inferred location, date problems, > 30-day-old “ongoing”) |
| `latitude, longitude` | From the geocoder or an operator – **never from the model** |
| `geo_status` | `APPROXIMATE`, `MANUAL`, `UNRESOLVED` |
| `geo_precision` | `LOCALITY`, `CITY`, `STATE`, `MANUAL` |
| `geo_method, geo_query, geo_display_name, geo_confidence` | `GAZETTEER`/`NOMINATIM`/`MANUAL`, query used, matched place, HIGH/MEDIUM/LOW |

## `incidents`

| Field | Description |
|---|---|
| `status` | `NEW → MONITORING → CONFIRMED → RESOLVED`, or `DISMISSED`. Allowed transitions are enforced and logged in `incident_history` |
| `category, severity, time_status, state, city, locality, road_name, highway_number` | Merged from linked articles (severity = highest reported) |
| `latitude, longitude, geo_precision` | Best-precision position among linked articles |
| `first_reported_at, last_reported_at` | From linked, non-rejected articles |
| `last_verified_at` | Last operator confirmation (approval or status change to CONFIRMED) |
| `article_count`, `has_conflict`, `conflict_notes` | Evidence count and recorded disagreements (severity ≥ 2 levels apart, start times > 48 h apart, “ongoing” after “resolved”) |

**Active** = status NEW/MONITORING/CONFIRMED **and** last report within `stale_after_hours` (default 72 h).
Older open incidents are **stale** and are never presented as current.

Linking rule: same category and city, within `link_window_hours` (default 72 h) and, when either report
names a highway/road/locality, those must agree. Area-wide categories (flooding, weather, VIP/security,
protest, congestion) without specifics may link by city; point events (accidents, closures…) may not.

## Other tables

| Table | Purpose |
|---|---|
| `incident_history` | Status changes with actor, time and note |
| `audit_log` | Corrections, reviews, status changes, source/setting changes, key set/delete (never the key value) |
| `sources`, `fetch_runs` | Source configuration/health and every fetch run’s counts and errors |
| `import_batches`, `import_row_errors` | Every import with counts; rejected rows with line number and reason |
| `jobs` | Background jobs (import, fetch, classify, model download) with progress |
| `geocode_cache` | Nominatim results incl. NOT_FOUND; errors retried after 1 h |
| `alerts` | In-app alerts, deduplicated per incident/status/rule |
| `app_settings` | Non-secret settings (branding, LLM provider settings, rules, map) |

Secrets are **not** stored in the database (see SETUP_GUIDE §7).
