# REST API

Base URL: `http://127.0.0.1:8000`. Interactive OpenAPI documentation: **`/api/docs`** (machine-readable at
`/api/openapi.json`).

Conventions
* JSON in/out. Times are UTC ISO-8601 with `Z`.
* Errors: `{"error": {"code": <http status>, "message": "..."}, "detail": ...}` with proper status codes
  (400 bad request, 401 token required, 404 not found, 409 conflict/invalid transition, 413 too large,
  415 unsupported file, 422 validation, 500 internal).
* Lists: `?page=1&page_size=25` (max 200) → `{items, total, page, page_size, pages}`.
* Multi-value filters are comma-separated: `?category=CLOSURE,DIVERSION`.
* `X-Operator: <name>` attributes changes in the audit log (not authentication).
* If `APP_ACCESS_TOKEN` is set: `Authorization: Bearer <token>` on all `/api/*` except `/api/health` and
  `/api/settings/public`.

## Health & system
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness |
| GET | `/api/ready` | Readiness checks (database, scheduler, data dir, UI build) |
| GET | `/api/system/info` | Version, paths, scheduler, LLM status, backups, internet requirements |
| POST | `/api/system/backup` | Create a database backup |

## Dashboard & reports
| GET | `/api/dashboard/summary?date_from&date_to&state&category` | All dashboard metrics, distributions, timeline, source health, activity |
|---|---|---|
| GET | `/api/quality` | Missing fields, geocoding precision, conflicts, stale incidents, failed classifications, measured source reliability, duplicate suggestions |
| GET | `/api/reports/summary?date_from&date_to&state` | Period summary report |

## Records
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/records` | Search/filter/sort. Filters: `q, category, severity, relevance, classification_status, review_status, prefilter, connector, time_status, geo_precision, source, state, city, highway, date_from, date_to, event_from, event_to, has_coords, needs_review, incident_id, include_near_duplicates`; `sort` = `published_at, ingested_at, title, source, severity, category, event_start, updated_at, city`; `order` = asc/desc |
| GET | `/api/records/facets` | Values for filter dropdowns |
| GET | `/api/records/export?format=csv\|json&<filters>` | Streamed export (≤ 50,000 rows) with provenance header |
| GET | `/api/records/{id}` | Article, current classification, history, sightings, incident, audit |
| GET | `/api/records/{id}/classifications/{cls_id}/raw` | Raw model output |
| PATCH | `/api/records/{id}/classification` | `{changes: {field: value}, note}` → new HUMAN version |
| POST | `/api/records/{id}/review` | `{decision: APPROVED\|REJECTED\|PENDING_REVIEW, note}` |
| POST | `/api/records/bulk-review` | `{ids: [...], decision, note}` |

## Classification & LLM
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/classification/run` | `{article_ids? , filters?, limit, provider?, reclassify}` → background job |
| GET | `/api/classification/stats` | Counts by status, review, relevance, model |
| GET/PUT | `/api/llm/config` | Provider settings (no secrets) |
| POST | `/api/llm/test` | `{provider}` – list models + tiny structured generation |
| GET | `/api/llm/models?provider=` | Model list |
| POST | `/api/llm/test-classification` | Classify a labelled test record (not stored) |
| GET | `/api/llm/ollama/status` | Ollama detection, hardware, recommendation |
| POST | `/api/llm/ollama/pull` | `{model, confirm: true}` → download job |
| GET | `/api/secrets` | Which keys are configured (never values) |
| PUT/DELETE | `/api/secrets/{NAME}` | Set (`{value}`) or remove a key |

## Incidents & map
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/incidents` | Filters: `q, status, category, severity, state, city, highway, date_from, date_to, lifecycle (active\|stale\|open\|resolved), has_conflict, source, classification (approved\|pending)` |
| GET | `/api/incidents/export?format=csv\|json` | Export |
| GET | `/api/incidents/{id}` | Incident, articles with evidence, history, allowed transitions |
| POST | `/api/incidents/{id}/status` | `{status, note}` (invalid transitions → 409) |
| POST | `/api/incidents/{id}/merge` | `{target_id, confirm: true, note}` |
| POST | `/api/incidents/{id}/detach` | `{article_id}` |
| GET | `/api/map/incidents` | GeoJSON (same filters, `include_state_level`) + `meta.mapped/unmapped` |

## Sources, imports, jobs, alerts, audit, settings
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/sources` | Sources with health, configuration status, scheduler state |
| PATCH | `/api/sources/{id}` | `enabled, poll_interval_minutes (≥30), max_records, timeout_seconds, max_retries, config` |
| POST | `/api/sources/{id}/fetch` | Fetch now (job; deduplicated) |
| POST | `/api/sources/{id}/test` | Real connectivity test (≤ 3 items, not stored) |
| GET | `/api/sources/{id}/runs` | Fetch history |
| GET | `/api/imports/files` | Importable files in the data folder |
| POST | `/api/imports/run` | `{paths: [...]}` (only inside the data/uploads folders) |
| POST | `/api/imports/upload` | multipart `file` (.jsonl/.ndjson/.json/.csv, size-limited) |
| GET | `/api/imports/batches`, `/api/imports/batches/{id}/errors.csv` | History and rejected-row report |
| GET | `/api/jobs`, `/api/jobs/{id}`; POST `/api/jobs/{id}/cancel` | Background jobs |
| GET | `/api/alerts`; POST `/api/alerts/{id}/read`, `/api/alerts/read-all` | In-app alerts |
| GET | `/api/audit?entity_type&entity_id` | Audit trail |
| GET | `/api/settings/public` | Branding, map, categories (no auth needed) |
| GET/PUT | `/api/settings/{branding\|classification\|incidents\|alerts\|map\|acquisition\|setup}` | Settings groups (validated) |
