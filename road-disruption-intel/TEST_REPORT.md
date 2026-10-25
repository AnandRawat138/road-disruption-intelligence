# Test report

## Update – version 1.1.0 (25 October 2026)

**Automated backend tests – 75 passed, 0 failed, 0 skipped** (56 from 1.0.0, one adjusted, 19 new in
`tests/test_5_highways_ml.py`).

| Area | Tests | Result |
|---|---|---|
| Highway extraction | `test_extract_highways` (10 cases: NH/SH numbers, *National Highway 66*, `NH44`, expressways, city-pair highways, Title-Case headlines, *NHAI* not a highway), `test_highway_aliases_share_one_id` | Passed |
| Highways API | `test_highways_api_lists_running_stale_and_unverified` (running vs stale vs unverified, resolved incidents excluded, search, stale toggle, detail, 404) | Passed |
| ML training and metrics | `test_ml_training_reports_honest_metrics` (cross-validated, above majority baseline, metric note present) | Passed |
| ML predictions grounded in text | `test_ml_predictions_are_grounded` (highway/city copied from text, highway names not used as the event city, severity/times never guessed, off-topic text irrelevant) | Passed |
| ML engine | `test_ml_engine_classifies_and_links_incident` | Passed |
| LLM unavailable → ML fallback | `test_llm_unavailable_falls_back_to_ml` (failed LLM attempt kept, ML version current), `test_classify_job_switches_to_ml_when_llm_unreachable` | Passed |
| ML never replaces LLM/human results | `test_ml_never_replaces_an_existing_llm_result` (fallback during reclassify keeps the LLM result; ML job skips LLM-classified records) | Passed |
| Engine settings & ML API | `test_engine_setting_and_ml_api` (validation, status, test endpoint, engine passed to jobs) | Passed |
| No-fallback behaviour | `test_permanent_provider_error_not_retried_forever` now runs with `ml_fallback` off | Passed |

Manual checks on a copy of the operational database (a second instance on port 8010, scheduler off, so the
running installation and its data were not touched):
* Highways page lists 33 highways for a 7-day report window and 51 for 30 days; selecting *Mumbai-Pune Expressway*
  and *NH-48* shows their incidents, reports and map. Desktop (1440 px) and phone (390 px) layouts checked.
* *Train now* trained `tfidf-logreg-…` on 1,299 records in about 6 s; metrics shown match `/api/ml/status`.
* With Ollama pointed at an unreachable port, a 6-record and a 4-record classification job reported
  “LLM ollama unavailable … using ML fallback”, classified every record (0 failed), and each record shows the
  fallback note and `ml / tfidf-logreg-…` as producer.
* Frontend type check and production build pass.

---
## Version 1.0.0

Date: 11 October 2026 · Machine: Windows 11, Python 3.12.7 (venv) / 3.14, Node 25.1, 16.5 GB RAM,
NVIDIA RTX 3060 Laptop (6 GB), Ollama 0.34.2.

## 1. Automated backend tests – 56 passed, 0 failed, 0 skipped

Run: `cd backend && ..\.venv\Scripts\python -m pytest tests -v`. External services are replaced by
`httpx.MockTransport`; no network, keys or paid credits are needed. A throw-away database is used.

| # | Requirement | Tests | Result |
|---|---|---|---|
| 1 | Application startup | `test_health_and_ready`, `test_security_headers_and_spa` | Passed |
| 2 | Database initialisation | `test_init_db_idempotent_and_backup_before_migration` (incl. backup before migration) | Passed |
| 3 | Historical import | `test_historical_import_and_dedup`, `test_csv_and_json_array_import`, `test_import_batches_listed`, `test_upload_endpoint` | Passed |
| 4 | Duplicate suppression | `test_url_canonicalisation`, `test_historical_import_and_dedup`, `test_reimport_is_idempotent`, `test_run_source_records_health_and_isolates_failures` | Passed |
| 5 | Malformed import handling | `test_malformed_rows_reported` (empty title, bad JSON, non-object, `javascript:` URL, no identifiers, 1890 date) | Passed |
| 6 | Source parsing (fixtures) | `test_google_news_rss_parsing`, `test_gdelt_parsing_and_rate_limit` | Passed |
| 7 | API pagination & filtering | `test_records_pagination_filters_and_sort`, `test_record_detail_and_404` | Passed |
| 8 | Classification schema validation | `test_validate_good_output`, `test_validate_rejects_fabrication_and_bad_values`, `test_validate_fatal_on_missing_relevance`, `test_extract_json_handles_fences_and_garbage` | Passed |
| 9 | Classification failure & retry | `test_classification_success_after_retry_and_incident`, `test_malformed_output_is_failure_not_success`, `test_permanent_provider_error_not_retried_forever`, `test_reclassification_keeps_approval_only_if_outcome_unchanged` | Passed |
| 10 | LLM configuration validation | `test_provider_config_validation`, `test_anthropic_tool_output_parsed` | Passed |
| 11 | Missing/invalid API keys | `test_provider_config_validation`, `test_invalid_api_key_is_auth_error`, `test_quota_exhausted_is_not_retryable`, `test_newsapi_not_configured_without_key` | Passed |
| 12 | Ollama unavailable / model missing | `test_ollama_unavailable_and_model_missing`, `test_llm_test_endpoint_reports_unreachable` | Passed |
| 13 | Geocoding cache & failures | `test_geocoder_cache_and_failures` (cache hit, far-match rejection, network error fallback, state-only, unresolved) | Passed |
| 14 | Invalid / missing coordinates | `test_geocoder_cache_and_failures`, `test_human_correction_creates_new_version` (coordinates outside India rejected), `test_incident_api_and_map`, `test_city_state_implies_city` | Passed |
| 15 | Incident status transitions | `test_status_transitions_alerts_and_resolution`, `test_separate_accidents_not_merged_but_same_closure_linked` | Passed |
| 16 | CSV/JSON export | `test_csv_and_json_export` | Passed |
| 18 | Health/readiness | `test_health_and_ready` | Passed |
| 19 | Permissions & secrets | `test_secrets_never_returned`, `test_log_redaction`, `test_gitignore_protects_secrets_and_runtime`, `test_access_token_enforced`, `test_server_refuses_unprotected_remote_bind`, `test_path_traversal_rejected`, `test_source_update_validation`, `test_env_file_not_committed` | Passed |
| 20 | Dashboard data | `test_dashboard_metrics_match_database` (metrics equal direct DB counts) | Passed |
| – | Concurrency regression | `test_no_write_lock_held_during_model_call` | Passed |
| – | Timestamp regression | `test_timestamps_are_utc_marked` | Passed |
| – | Connector resilience | `test_retry_on_5xx_then_success`, `test_auth_failure_not_retried`, `test_timeout_is_bounded` | Passed |
| – | Settings | `test_settings_validation`, `test_settings_store_merge` | Passed |

Warning (not a failure): Starlette’s test client prints a deprecation notice about `httpx`.

Not automated: browser end-to-end tests (no browser-automation framework in the project). The journeys below
were executed manually in a real browser.

## 2. Frontend

| Check | Result |
|---|---|
| TypeScript type check (`tsc`, strict, no unused locals) | Passed |
| Production build (`npm run build`) | Passed – 1.09 MB JS (306 KB gzip), 80 KB CSS |

## 3. Manual end-to-end journeys (real browser, real data)

| Journey | Steps performed | Result |
|---|---|---|
| A. Start → import → dashboard | `setup_and_start.bat`; historical import of all 8 sources; Overview shows 78,415 source rows / 14,809 unique articles (now 15,100 after live fetches), figures equal DB counts | Passed |
| B. Configure LLM → test → classify | LLM page: Ollama test *Connected, llama3:8b answered in 2.2 s*; test classification; bulk classification jobs | Passed |
| B′. Cloud key | An `OPENAI_API_KEY` already present in this PC’s environment: model list succeeded, generation returned **HTTP 429 – no credits remaining**. Shown correctly; now classified as non-retryable QUOTA | Provider reached; **not usable** (account has no credit) |
| C. Fetch → dedup → classify → review → approve | Scheduled Google News fetch: 300 items, 291 new, 9 duplicates; classified with llama3:8b; approved one record (“Red Road Closure … Kolkata”) as operator “QA Tester” → incident CONFIRMED, HIGH alert raised, audit entry recorded | Passed |
| D. Map → filter → marker → evidence | Clusters, fly-to on list selection, evidence panel with excerpt and source link, lifecycle buttons, fit/reset, focus region; desktop and 375 px phone width | Passed (after fixes listed below) |
| E. Export | CSV/JSON export endpoints verified by automated test; download buttons use the same endpoints | Passed (API); browser download not exercised |
| F. Restart → persistence | Stopped with a classification job running → job recorded INTERRUPTED, queued records released; restarted → articles, classifications, settings and approvals persisted; job resumed skipping finished records | Passed |

## 4. Windows scripts (executed on this PC)

| Script | Scenario | Result |
|---|---|---|
| `setup_and_start.bat` | Existing install: skipped venv, installed packages once, then “already up to date” on re-run; created `.env` once, then “kept unchanged” | Passed |
| `setup_and_start.bat` | **Fresh copy in a folder with spaces**: created venv (Python 3.12.7), installed packages, created DB, started | Passed (51 s) |
| `start.bat` | Start (ready in 4 s), second start detects running instance, port held by **another copy** → error code 20 with advice, alternate port via `.env` | Passed (ownership bug found and fixed) |
| `stop.bat` | Graceful stop (≈3 s, “Shutdown complete”), not-running case, force-stop fallback, stopping one copy leaves the other running | Passed |
| `setup_llm.bat` / `rdi.ollama_cli` | Detection, hardware, recommendation (qwen2.5:7b), cancel path – nothing changed | Passed (download path not executed to avoid a 4.7 GB download) |
| `diagnose.bat` | All checks; Google News/Nominatim/map tiles HTTP 200 | Passed (Nominatim check fixed to send a User-Agent) |
| `rdi.cli backup/restore` | Backup, restore refusal without `--yes`, restore with safety backup, path traversal refused | Passed |

## 5. Live external services

| Service | Result |
|---|---|
| Google News RSS | Working – live fetches stored new articles |
| GDELT DOC API | HTTP 429 on every attempt from this network (also with `curl`, 6 s apart) – reported as RATE_LIMITED |
| Nominatim | Working with identifying User-Agent; results cached |
| OpenFreeMap tiles | Working |
| Ollama (llama3:8b) | Working; 8–17 s per record on this GPU |
| OpenAI | Reached; account has no credits (HTTP 429) |
| NewsAPI, GNews, Anthropic, Reddit | No credentials available – mocked tests only (UNVERIFIED) |

## 6. Classification quality (observed, not a formal evaluation)

No ground-truth labels exist in the delivered data, so accuracy was **not measured**. Observations:
* Prompt v1.0 with llama3:8b put 76 of 178 relevant records into OTHER (e.g. announced diversions). Prompt v1.1
  added category definitions; a 6-headline spot check went from 2/6 to 6/6 correct relevance and plausible
  categories. Records are being reclassified with v1.1.
* Most historical records are headline-only, so severity is usually UNKNOWN and event times are rarely stated.

## 7. Issues found during testing and fixed
See AUDIT_REPORT.md §5 (11 defects, each fixed and, where practical, covered by a regression test).
