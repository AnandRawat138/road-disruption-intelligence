# Client handover – Road Disruption Intelligence v1.0

For: Aviral Consulting (OPC) Private Limited, Mumbai. Date: 11 October 2026.

## 1. What you are receiving

A local web application that collects Indian road-disruption news, classifies each article with an AI model you
control, groups related reports into incidents, and presents them on a dashboard, records table and map, with an
operator review workflow, exports and reports. It runs on one Windows PC; no cloud service is required except the
news sources and map tiles.

## 2. Daily operation

1. `start.bat` → browser opens at http://127.0.0.1:8000/. Type your name in **Operator** (top right).
2. **Overview** – check *Last live refresh*, *Active incidents* and *Awaiting review*.
3. **Classification queue** – open each record, read the original headline and evidence, then **Approve**,
   **Reject** or **Edit fields**. Approving confirms the incident.
4. **Disruptions / Interactive map** – current situation. *Stale* means “no recent report”, not “ongoing”.
5. **Sources & acquisition** – *Fetch now* for an immediate update; polling runs automatically every 3 hours.
6. **News & records → Classify all matching** – to classify more historical or new records.
7. `stop.bat` at the end of the day (optional – it can run continuously).

## 3. Current state of the data (at handover)

| Item | Value |
|---|---|
| Historical rows imported | 78,415 rows from 8 sources → 14,809 unique articles (0 invalid, 0 failed) |
| Live articles fetched (Google News) | 291 new on 11 Oct 2026 (total unique now 15,100) |
| Classified | ≈ 250 at the time of writing; a background job is classifying ~740 more *likely relevant* records from Aug–Oct 2026 (~10–17 s each) |
| Unclassified | ≈ 14,800 – mostly older or keyword-*unlikely* articles. Classify them selectively (newest/likely-relevant first) |
| Incidents | ≈ 220 (≈ 48 active, the rest stale or resolved) – grows as classification continues |
| Test action | One record (“Red Road Closure Triggers Kolkata Traffic Gridlock”) was approved by **“QA Tester”** during acceptance testing; please re-review it |

The previously reported dataset totals (e.g. “8,914 weak-labelled events”) are **not** classifications – that
file contains no labels. Only records classified in this application have categories, locations and severities.

## 4. Verified vs. not verified

| Capability | Status |
|---|---|
| Historical import, deduplication, error reports | **Verified** on the real data |
| Google News RSS acquisition and scheduling | **Verified live** |
| GDELT | Implemented; **live attempts rate-limited (HTTP 429)** from this network; disabled by default |
| NewsAPI, GNews, Reddit, custom RSS | Implemented and tested with mocks; **not configured** (need your keys/feeds) |
| Local LLM (Ollama, llama3:8b) | **Verified live**; quality acceptable for triage, needs operator review |
| OpenAI-compatible | Implemented; the key found on this PC **reached OpenAI but has no credit** (HTTP 429) |
| Anthropic | Implemented, tested with mocks; **not verified live** (no key) |
| Geocoding | **Verified**: offline gazetteer + Nominatim (cached, 1 request/second) |
| Map (OpenFreeMap tiles) | **Verified** desktop + phone width |
| Windows scripts | **Verified** on this PC including a fresh install in a path with spaces |
| Classification accuracy | **Not measured** – no labelled evaluation data exists |

## 5. Known limitations

* **Headline-only evidence.** Google News RSS and the historical data contain headlines and publishers only, so
  severity, exact times and road names are often unknown. The application does not scrape publisher websites.
* **Approximate locations.** Points are city or locality centroids; more than half of the incidents (≈ 59 % at handover) have no usable location yet.
  The map never shows routed road segments – that would require a road-network service and was deliberately not
  faked.
* **Model quality.** Small local models make mistakes (e.g. category OTHER, wrong relevance). The review workflow
  is essential; a larger local model or a cloud model improves results.
* **Coverage.** News sources are samples; absence of a record does not mean absence of a disruption.
* **Speed.** ~10–17 s per record locally on a 6 GB GPU (≈ 250–350 records/hour); classifying all 15,000 records would
  take days. Prioritise by date and pre-filter.
* **Single user / single PC.** Operator names are attribution only, not logins. No email/SMS alerts.
* **Secrets file not encrypted** (protected by Windows permissions only).
* Legacy v0 events (30, partly hand-written by seed scripts) were not migrated; the v0 database is backed up.

## 6. Recommended next steps

1. Decide on the production LLM (e.g. `qwen2.5:7b` via `setup_llm.bat`, or a funded cloud key) and reclassify.
2. Add official feeds (traffic police / NHAI / disaster management RSS where permitted) under *Sources*.
3. Obtain NewsAPI/GNews keys if broader coverage is needed (check their commercial terms).
4. Label a sample of ~300 records to measure accuracy before relying on automated categories.
5. For multi-user or remote access: put the app behind HTTPS with real user accounts.

## Security checklist

| Control | Status |
|---|---|
| Binds to 127.0.0.1 by default | Yes |
| Network exposure refused without `APP_ALLOW_REMOTE=true` **and** a ≥16-character `APP_ACCESS_TOKEN` | Yes (tested) |
| Access token required on all API routes when configured (except liveness/branding) | Yes (tested) |
| API keys only server-side (env/.env or `runtime/secrets.json`), never returned to the browser | Yes (tested) |
| Keys redacted from logs; not in exports, diagnostics or audit log | Yes (tested) |
| `.env`, `runtime/` (DB, logs, secrets, backups) gitignored; `.env.example` has placeholders only | Yes (tested) |
| Upload validation (extension, size, binary check, sanitised names) and path-traversal protection | Yes (tested) |
| No endpoint gives raw database or filesystem access | Yes |
| Security headers (CSP, nosniff, frame denial, no referrer) | Yes |
| Destructive actions need confirmation (reject, dismiss, merge, key removal, restore) | Yes |
| Audit trail of corrections, reviews, status changes, settings and key changes | Yes |
| HTTPS | **No** – plain HTTP; acceptable for localhost only |
| User authentication / roles | **No** – single shared token at most |
| Encrypted secret storage | **No** |

## Go-live assessment

| Stage | Assessment | Basis |
|---|---|---|
| **Local demonstration** | **Ready** | All features work end to end on this PC with real data; 56 automated tests pass; scripts verified |
| **Controlled client pilot** (one PC, trained operators reviewing every record) | **Ready with conditions** | Requires: choosing and testing the production LLM, finishing classification of the target period, operators reviewing the queue, accepting headline-only evidence and approximate locations |
| **Production deployment** (multi-user, unattended, decisions relying on output) | **Not ready** | No user accounts/HTTPS, accuracy not measured, coverage limited to one verified free source, no encrypted secrets, no monitoring/alerting outside the app |
