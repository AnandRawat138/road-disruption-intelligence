# Changelog

## 1.0.0 – 11 October 2026

Complete rebuild of the application as a client-ready local deployment. See AUDIT_REPORT.md for the
reasons behind each change.

### Added
* `backend/rdi` – new FastAPI application: versioned SQLite schema with automatic pre-migration backups,
  background job runner, single-instance scheduler, structured JSON logs with secret redaction.
* Historical import of `data/` (JSONL/JSON/CSV + legacy v0 SQLite) – idempotent, provenance-preserving,
  error reports. 78,415 rows → 14,809 unique articles on first import.
* Source connectors with health tracking: Google News RSS, GDELT DOC 2.0, NewsAPI.org, GNews.io, Reddit OAuth,
  custom/official RSS feeds.
* LLM classification with providers Ollama, OpenAI-compatible and Anthropic; schema-constrained output;
  validation (fabricated roads/highways/dates removed, evidence verified); append-only versions; human corrections;
  review/approval workflow; reclassification on prompt/model change.
* Geocoding: offline gazetteer of Indian states/cities, cached and rate-limited Nominatim, precision labels.
* Incidents: linking of related reports, lifecycle, history, conflict detection, stale detection, merge/detach,
  in-app alerts.
* Web UI (React/TypeScript): Overview, Disruptions, Interactive map, News & records, Classification queue, Alerts,
  Analytics & reports, Sources & acquisition, Data import, LLM configuration, Settings & health.
* Exports (CSV/JSON) for records and incidents; printable period report; data-quality report.
* Windows scripts: `setup_and_start.bat`, `start.bat`, `stop.bat`, `setup_llm.bat`, `diagnose.bat`.
* 56 automated tests; documentation set.

### Changed
* Default polling reduced from 119 requests per ~1-minute cycle to 12 queries every 3 hours per source.
* Default binding is 127.0.0.1; network exposure requires an access token.
* Basemap switched to OpenFreeMap (OpenStreetMap data, free for commercial use, attribution shown).

### Removed / disabled
* `[DEMO]` mock articles returned by the old NewsAPI provider.
* Legacy seed scripts (`backend/seed_2026.py`, `backend/seed_user_10.py`) – disabled with a guard; they deleted
  all data and inserted hand-written events.
* “Disruption-aware routing” (fabricated detour waypoint) – not part of v1.
* Celery/Redis/PostGIS Docker stack – superseded by the simpler single-process architecture
  (`docker-compose.yml` left in place for reference only; it does not run v1).

### Legacy
* The v0 backend (`backend/app`), research scripts, results and the original README (`docs/LEGACY_README_v0.md`)
  are kept unmodified for reference. The v0 database is backed up in `runtime/backups/`.
