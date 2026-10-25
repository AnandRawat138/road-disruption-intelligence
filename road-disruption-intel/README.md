# Road Disruption Intelligence

**AI-based road disruption intelligence and mapping platform**
Prepared for **Aviral Consulting (OPC) Private Limited**, Mumbai, Maharashtra, India.

The application collects news about road disruptions in India (closures, diversions, accidents,
flooding, landslides, protests, VIP movements, construction and more), uses a language model – or a
built-in machine-learning classifier when no language model is available – to turn each article into a
structured record, groups related reports into incidents, and shows them on a dashboard, a per-highway
view, a searchable records table and an interactive map. Operators review and approve the model's
output before it is treated as confirmed.

> **Important:** this tool summarises *news reports*. It does not have live traffic sensors, does not
> guarantee complete coverage, and its map positions are approximate. Always check the linked source
> before acting on a record.

---

## Quick start (Windows)

1. Make sure **Python 3.11 or newer** is installed ([python.org](https://www.python.org/downloads/windows/),
   tick *“Add python.exe to PATH”*). Node.js is **not** needed – the interface is pre-built.
2. Double-click **`setup_and_start.bat`**. The first run creates a private Python environment, installs
   packages (internet needed), prepares the database and offers to import the historical data.
3. Your browser opens at **http://127.0.0.1:8000/**.

Afterwards use **`start.bat`** to start and **`stop.bat`** to stop. How to use every screen:
[docs/USER_GUIDE.md](docs/USER_GUIDE.md). Installation details:
[SETUP_GUIDE.md](SETUP_GUIDE.md). Problems: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

| Script | What it does |
|---|---|
| `setup_and_start.bat` | First-time setup (safe to re-run), then starts the app |
| `start.bat` | Starts the app; detects an already-running copy; checks the port |
| `stop.bat` | Graceful stop of *this* application only |
| `setup_llm.bat` | Optional: install/choose a local Ollama model (asks before downloading) |
| `diagnose.bat` | Read-only checks of Python, database, port, Ollama and internet access |

---

## Main features

| Area | What you can do |
|---|---|
| **Overview** | Live metrics from the database (records, relevant reports, review queue, active / stale incidents), category/state/city/severity charts, daily volumes, source health, recent activity. Every number links to the matching records. |
| **Disruptions** | Incidents built from related reports, with lifecycle *New → Monitoring → Confirmed → Resolved / Dismissed*, status history, conflict notes, merge and detach. Open incidents with no recent report are shown as **stale**, never as current. |
| **Highways** | Every national highway, state highway, expressway and named highway (e.g. *Mumbai-Goa Highway*) named in an open incident or a recent unclassified report, with running / stale / unverified counts, search (`NH-48`, `Yamuna`, `Mumbai-Pune`), type and time filters, and a detail panel with incidents, reports and an approximate map. Spelling variants are merged (*Pune-Mumbai* = *Mumbai-Pune*, *Gurgaon* = *Gurugram*). |
| **Interactive map** | Clustered incident map (India default, focus on Mumbai and other cities), severity colour + category letters, filters shared with the list, time filter, *Fit to results*, *Reset view*, evidence panel with source links. Approximate positions are marked as approximate. |
| **News & records** | Server-side search (keyword, city, road, `NH-48`, source), multi-filters, sorting, pagination, row selection, bulk classify/approve/reject, CSV/JSON export, detail panel with original text, evidence excerpt, model output, validation notes, history, provenance and audit trail. |
| **Classification queue** | Records waiting for review, with the reasons they were flagged. Approve, reject or correct fields (corrections are stored as new human versions). |
| **Sources & acquisition** | Per-source enable/schedule, search terms, places, limits, timeouts, retries, *Fetch now*, connection test, run history and health. |
| **Data import** | Import the historical `data/` files or upload JSONL/JSON/CSV. Real counts (discovered, imported, duplicate, invalid, failed, skipped) and a downloadable error report. |
| **Classification engine** | Choose the **LLM** or the built-in **ML model** in Settings. LLM: local Ollama or your own OpenAI-compatible / Anthropic key, connection test, model list, hardware-based model recommendation, model download with confirmation, test classification. ML: TF-IDF + logistic regression trained on the application's own labelled records, cross-validated metrics, *Retrain now*, test box. **Automatic ML fallback** when the LLM is unavailable (each such record says so). |
| **Analytics & reports** | Printable period summary (save as PDF from the browser), data-quality report, measured source reliability, duplicate-incident suggestions. |
| **Settings & health** | Branding, workflow rules, alert rules, map style, API keys, health checks, backups, audit trail. |

## News sources and their real status

| Source | Access | Status on the development machine (11 Oct 2026) |
|---|---|---|
| Google News RSS | Free, no key | **Verified** – live fetches returned new articles |
| GDELT DOC 2.0 API | Free, no key, ≤1 request / 5 s | **Rate-limited (HTTP 429)** on every attempt from this network; disabled by default |
| NewsAPI.org | Your `NEWSAPI_KEY` (free plan is development-only) | Not configured – tested with mocked responses only |
| GNews.io | Your `GNEWS_API_KEY` | Not configured – tested with mocked responses only |
| Reddit | Reddit OAuth app (client id/secret) | Not configured – unauthenticated access returns HTTP 403 |
| Official / custom RSS feeds | Feed URLs you are permitted to poll | Not configured (add URLs in *Sources*) |
| Historical files (`data/`) | Local | **Imported** – 78,415 rows → 14,809 unique articles |

## Language models

* **Local (default):** Ollama – data stays on the computer, no API cost. Tested with `llama3:8b`
  on an RTX 3060 (6 GB): about 8–15 s per record.
* **Cloud (your key):** any OpenAI-compatible endpoint or Anthropic. Implemented and tested with mocked
  responses; a live test needs your key.

The model never supplies coordinates and its output is validated: road names, highway numbers and dates
not found in the article are removed, evidence excerpts are checked against the source text, and doubtful
records are flagged for review. Model “confidence” is the model’s own judgement, **not** a calibrated
probability.

## Built-in ML classifier

* **What:** TF-IDF word and character n-grams with logistic regression (scikit-learn), three models –
  relevance, category and time status. Code: `backend/rdi/services/ml/`.
* **Trained on:** current LLM and human classifications in the database (approved and corrected records
  weigh 3×, rejected records and ML outputs are excluded) and a bundled seed set (`seed_labels.jsonl`:
  449 LLM/operator-labelled headlines plus 850 weak negatives that the keyword pre-filter rates as unlikely). It trains automatically when first
  needed (about 10 s) and can be retrained from the UI.
* **Measured on the current data** (5-fold cross-validation, agreement with the training labels, which are
  mostly LLM labels – not verified accuracy): relevance 96 % accuracy (majority baseline 67 %), category
  75 % accuracy / 0.58 macro-F1 (baseline 46 %), time status 83 % (baseline 64 %).
* **Limits:** it never sets severity or event times (they stay *unknown*), and copies highway, road and city
  names only when they appear in the text. The LLM remains the more complete extractor; use ML when no LLM
  is available or for very large backlogs.

## What needs internet

Live news sources, online geocoding (Nominatim), map tiles, cloud LLMs, and installing Ollama/models.
Browsing, searching, exporting, importing, reviewing, classifying with the ML model, and classifying with an
already-downloaded local model work offline (the map background will be blank offline).

## Documentation

* [docs/USER_GUIDE.md](docs/USER_GUIDE.md) – **step-by-step user guide with screenshots**
* [SETUP_GUIDE.md](SETUP_GUIDE.md) – installation, configuration, keys, Ollama, backups
* [CLIENT_HANDOVER.md](CLIENT_HANDOVER.md) – day-to-day operation, verified vs. unverified, go-live status
* [TROUBLESHOOTING.md](TROUBLESHOOTING.md) – common problems and fixes
* [DATA_DICTIONARY.md](DATA_DICTIONARY.md) – every stored field and status value
* [docs/API.md](docs/API.md) – REST API (interactive docs at `/api/docs` while running)
* [AUDIT_REPORT.md](AUDIT_REPORT.md) – audit of the previous version and what was fixed
* [TEST_REPORT.md](TEST_REPORT.md) – automated and manual test results
* [CHANGELOG.md](CHANGELOG.md)

## Project layout

```
road-disruption-intel/
  setup_and_start.bat  start.bat  stop.bat  setup_llm.bat  diagnose.bat
  .env.example            configuration template (copy to .env; .env is never committed)
  backend/
    rdi/                  application (FastAPI, SQLAlchemy, services, API)
      services/ml/        built-in ML classifier and its seed labels
      services/highways.py  highway-name extraction and the per-highway view
    tests/                automated tests (pytest, no network needed)
    requirements.txt
    app/, seed_*.py ...   previous version (v0), kept for reference only – not used
  frontend/
    src/app/              React + TypeScript interface
    dist/                 pre-built interface served by the backend
  scripts/process_tools.ps1   process checks used by start/stop
  runtime/                created on first start: database, logs, backups, uploads, secrets (gitignored)
  docs/
../data/                  historical data (read-only; never modified)
```

## Security summary

Local-only by default (binds to 127.0.0.1). Network exposure is refused unless an access token is
configured. API keys stay on the server (environment or `runtime/secrets.json`, not encrypted – protected
by Windows file permissions), are never sent to the browser and are redacted from logs. See
[CLIENT_HANDOVER.md](CLIENT_HANDOVER.md#security-checklist).

---
© Aviral Consulting (OPC) Private Limited. Map data © OpenStreetMap contributors; basemap by OpenFreeMap.
