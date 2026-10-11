# Road Disruption Intelligence

**AI-based road disruption intelligence and mapping platform for India**
Built for **Aviral Consulting (OPC) Private Limited**, Mumbai, Maharashtra, India.

The application collects news about road disruptions in India – closures, diversions, accidents, flooding,
landslides, protests, VIP movements, construction and more – uses a language model that **you control** (local
Ollama or your own API key) to turn each article into a structured record, groups related reports into incidents,
and presents everything on a dashboard, a searchable records table and an interactive map. Operators review and
approve the AI output before it is treated as confirmed.

![Overview dashboard](road-disruption-intel/docs/screenshots/01-overview.png)

> **Please note:** the system summarises *news reports*. It has no live traffic sensors, does not guarantee
> complete coverage, and map positions are approximate (city/locality centres). Always check the linked source
> before acting on a record.

---

## Contents
- [Features](#features)
- [Screenshots](#screenshots)
- [Requirements](#requirements)
- [Installation](#installation)
- [First use – step by step](#first-use--step-by-step)
- [Daily use](#daily-use)
- [Configuration](#configuration)
- [News sources and AI models](#news-sources-and-ai-models)
- [Repository layout](#repository-layout)
- [Documentation](#documentation)
- [For developers](#for-developers)
- [Status and limitations](#status-and-limitations)

---

## Features

| Area | What you can do |
|---|---|
| **Overview** | Live metrics (records, relevant reports, review queue, active/stale incidents), charts by category, state, city and severity, daily volumes, source health and recent activity – every number is a database count and every figure is clickable |
| **Disruptions** | Incidents built from related reports, lifecycle *New → Monitoring → Confirmed → Resolved / Dismissed*, history, conflict notes, merge/detach; old open incidents are marked **stale**, never shown as current |
| **Interactive map** | Clustered incidents over India with severity colours and category letters, filters synced with the list, time filter, *Fit to results*, *Reset view*, focus on Mumbai/Delhi/Pune…, evidence panel with source links |
| **News & records** | Server-side search (keywords, places, `NH-48`, sources), multi-filters, sorting, pagination, bulk classify/approve/reject, CSV/JSON export, full detail with original text, evidence, history, provenance and audit trail |
| **Classification queue** | Records awaiting review with reasons they were flagged; approve, reject or correct fields |
| **Sources & acquisition** | Google News RSS (no key), GDELT, NewsAPI, GNews, Reddit, official RSS feeds – enable, schedule, test, *Fetch now*, health and run history |
| **Data import** | Import historical JSONL/JSON/CSV files or the legacy database; safe to repeat; real counts and downloadable error reports |
| **LLM configuration** | Local Ollama or OpenAI-compatible / Anthropic with your key; connection test, model list, hardware-based recommendation, model download with confirmation, test classification |
| **Reports** | Printable period summary (save as PDF), data-quality report, measured source reliability, duplicate suggestions |
| **Settings & health** | Branding, workflow and alert rules, API keys, health checks, backups, audit trail |

## Screenshots

| | |
|---|---|
| ![Map](road-disruption-intel/docs/screenshots/05-map.png) **Interactive map** | ![Map selection](road-disruption-intel/docs/screenshots/06-map-selected.png) **Incident evidence on the map** |
| ![Records](road-disruption-intel/docs/screenshots/07-records.png) **Records table** | ![Record detail](road-disruption-intel/docs/screenshots/08-record-detail.png) **Record with AI output and evidence** |
| ![Disruptions](road-disruption-intel/docs/screenshots/03-disruptions.png) **Active disruptions** | ![Sources](road-disruption-intel/docs/screenshots/11-sources.png) **Source health** |
| ![LLM](road-disruption-intel/docs/screenshots/13-llm-config.png) **LLM configuration** | ![Reports](road-disruption-intel/docs/screenshots/15-reports.png) **Summary report** |

More in the [User Guide](road-disruption-intel/docs/USER_GUIDE.md).

---

## Requirements

| Item | Needed? | Notes |
|---|---|---|
| Windows 10 (version 1803 or later) or Windows 11 | Yes | The start/stop scripts are Windows batch files |
| **Python 3.11 – 3.14** | Yes | Download from [python.org/downloads/windows](https://www.python.org/downloads/windows/). During installation tick **“Add python.exe to PATH”** |
| Internet connection | First setup | To install Python packages. Later for live news, geocoding and map tiles |
| Ollama | Optional | Free local AI – [ollama.com/download/windows](https://ollama.com/download/windows). Or use your own OpenAI/Anthropic key |
| Node.js | No | The web interface is already built (`frontend/dist`). Only needed if you change the interface code |
| GPU | Optional | Makes local AI faster; not required |
| Disk space | ~1 GB | Plus 2–9 GB per local AI model |
| Administrator rights | No | Everything installs inside the project folder |

---

## Installation

### Step 1 – Install Python
1. Open [python.org/downloads/windows](https://www.python.org/downloads/windows/) and download the latest
   **Python 3.12** (or newer) *Windows installer (64-bit)*.
2. Run it, tick **“Add python.exe to PATH”**, click **Install Now**.
3. Check: open *Command Prompt* and type `python --version` – it should print `Python 3.12.x` or newer.

### Step 2 – Download this project
**Option A – Download ZIP (no tools needed):** on this GitHub page click **Code → Download ZIP**, then extract it,
for example to `D:\RoadIntel`. Avoid extracting inside OneDrive/Downloads if possible.

**Option B – Git:**
```bash
git clone https://github.com/AnandRawat138/road-disruption-intelligence.git
```

After extracting you should have:
```
<folder>\
  data\                    historical news data
  road-disruption-intel\   the application
  README.md
```
Keep `data` and `road-disruption-intel` side by side – the application finds the data automatically.

### Step 3 – Run the setup
Open the `road-disruption-intel` folder and double-click **`setup_and_start.bat`**.

If Windows shows *“Windows protected your PC”*, click **More info → Run anyway** (the script only installs into the
project folder and needs no administrator rights).

The setup runs seven numbered stages and explains any problem instead of closing:

```
[1/7] Checking Python (3.11 or newer)...
      Using Python 3.12.7
[2/7] Creating the Python virtual environment (.venv)...
[3/7] Backend packages...
      Installing from PyPI (internet connection required)...
      Installed.
[4/7] Web interface...
      Pre-built interface found (frontend\dist). Node.js is not required.
[5/7] Configuration and database...
      Created .env from .env.example (local-only defaults; no keys).
      Created new database.
[6/7] Historical data...
      No import has been run yet. Import the historical data now (takes a few minutes) [Y,N]?
[7/7] Local LLM (optional)...
      Ollama is running. Use setup_llm.bat or the LLM configuration page to choose a model.

Setup complete. Starting the application...
 Road Disruption Intelligence is running:  http://127.0.0.1:8000/
```

Press **Y** at stage 6 to import the historical data (about 2–4 minutes for ~78,000 rows). Your browser then
opens at **http://127.0.0.1:8000/**.

Running `setup_and_start.bat` again later is safe – it skips everything already done and never deletes data or
overwrites your `.env`.

### Step 4 (optional) – Local AI model
Double-click **`setup_llm.bat`**. It checks whether Ollama is installed (and offers to open the official download
page if not), checks your RAM/GPU/disk, recommends a model, and **downloads only after you confirm**:

```
Hardware: 16.5 GB RAM, NVIDIA GeForce RTX 3060 Laptop GPU (6.0 GB), 32.4 GB free disk
Available choices:
  1.  llama3.2:3b      download ~2.0 GB     needs 8+ GB RAM   [GPU]
  2. *qwen2.5:7b       download ~4.7 GB     needs 12+ GB RAM  [GPU]   Recommended default for 16 GB machines.
  3.  llama3:8b        installed            needs 12+ GB RAM  [GPU]   Tested with this application.
  ...
Choose a model [2]:
```

Alternatively use your own cloud key – see the [User Guide §6](road-disruption-intel/docs/USER_GUIDE.md#6-setting-up-the-ai-model-llm).

### Scripts

| Script | Purpose |
|---|---|
| `setup_and_start.bat` | First-time setup (safe to re-run), then start |
| `start.bat` | Start; detects an already-running copy; checks the port; opens the browser |
| `stop.bat` | Graceful stop of this application only |
| `setup_llm.bat` | Optional local AI setup (asks before downloading) |
| `diagnose.bat` | Read-only checks: Python, database, port, Ollama, internet |

---

## First use – step by step

The **Getting started** box on the Overview page tracks these steps automatically. Full details with screenshots:
**[User Guide](road-disruption-intel/docs/USER_GUIDE.md)**.

1. **Enter your name** in the *Operator* box (top right). It is recorded in the audit trail.
2. **Import data** – *Data import* → select files → **Import selected** (skip if you pressed **Y** during setup).
   ![Data import](road-disruption-intel/docs/screenshots/12-data-import.png)
3. **Set up the AI** – *LLM configuration* → choose *Local Ollama* (or your provider), enter the model name,
   **Save configuration** → **Test connection** until it says *Connected*.
4. **Fetch current news** – *Sources & acquisition* → *Google News – India* → **Fetch now**.
5. **Classify** – *News & records* → filter *Pre-filter: Likely relevant* and *Classification: Unclassified* →
   **Classify all matching (max 100)** → **Start**. Watch the progress bar.
6. **Review** – *Classification queue* → open each record → read the original text and evidence → **Approve**,
   **Reject** or **Edit fields**.
   ![Review a record](road-disruption-intel/docs/screenshots/09-record-detail-actions.png)
7. **Monitor** – *Overview*, *Disruptions* and *Interactive map* now show your confirmed incidents.
8. **Export or report** – *Export CSV/JSON* on *News & records* or *Disruptions*; *Analytics & reports* →
   **Generate** → **Print / save as PDF**.

## Daily use

| Task | Where |
|---|---|
| Start / stop | `start.bat` / `stop.bat` |
| What is happening now? | *Overview* → *Active incidents*, *Interactive map* (lifecycle **Active**) |
| Get the latest news | Automatic every 3 hours, or *Sources* → **Fetch now** |
| Check the AI’s work | *Classification queue* (tick **Flagged only** first) |
| Find something | *News & records* search, e.g. `NH-48`, `Andheri`, `waterlogging` |
| Share | Export CSV/JSON or print the summary report to PDF |
| Back up | *Settings & health* → *Health & backups* → **Back up now** |

## Configuration

Optional settings are in `road-disruption-intel\.env` (created from `.env.example` during setup; never committed):

| Setting | Default | Meaning |
|---|---|---|
| `APP_PORT` | `8000` | Change if another program uses port 8000 |
| `APP_HOST` | `127.0.0.1` | Local-only access |
| `APP_ALLOW_REMOTE` + `APP_ACCESS_TOKEN` | off | Both required to allow other computers |
| `HISTORICAL_DATA_DIR` | auto | Location of the `data` folder |
| `SCHEDULER_ENABLED` | `true` | Automatic polling of enabled sources |
| `GEOCODING_ONLINE` | `true` | Use OpenStreetMap Nominatim for localities |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `NEWSAPI_KEY`, `GNEWS_API_KEY`, `REDDIT_CLIENT_ID/SECRET` | empty | Optional keys (can also be entered in the web UI) |

Restart (`stop.bat`, `start.bat`) after editing. Details: [SETUP_GUIDE.md](road-disruption-intel/SETUP_GUIDE.md).

API keys entered in the UI are stored only on your computer in `runtime\secrets.json` (plain JSON protected by
Windows file permissions, **not encrypted**), are never sent to the browser and are hidden in logs.

## News sources and AI models

| Source | Access | Tested status (11 Oct 2026) |
|---|---|---|
| Google News RSS | Free, no key | **Working** – live fetches stored new articles |
| GDELT DOC API | Free, ≤ 1 request / 5 s | Rate-limited (HTTP 429) from the development network; disabled by default |
| NewsAPI.org / GNews.io | Your key | Implemented, tested with simulated responses; needs your key |
| Reddit | Reddit OAuth app | Implemented; needs client id/secret |
| Official / custom RSS | Feed URLs | Add URLs in *Sources* |
| Historical files (`data/`) | Local | 78,415 rows → 14,809 unique articles |

| AI provider | Status |
|---|---|
| Ollama (local) | **Working** with `llama3:8b` (≈ 10–17 s per record on a 6 GB GPU) |
| OpenAI / OpenAI-compatible | Implemented; needs a key with credit |
| Anthropic | Implemented; needs a key |

The AI never supplies map coordinates, and its output is checked: road names, highway numbers and dates not found
in the article are removed, and evidence quotes are verified against the source text.

**Needs internet:** live news, online geocoding, map tiles, cloud AI, installing Ollama/models.
**Works offline:** browsing, search, export, import, review, and classification with an already-downloaded local model.

## Repository layout

```
data/                         historical news data (JSONL; read-only input)
road-disruption-intel/
  setup_and_start.bat  start.bat  stop.bat  setup_llm.bat  diagnose.bat
  .env.example                configuration template
  backend/
    rdi/                      application (FastAPI, SQLAlchemy, services, REST API)
    tests/                    automated tests (pytest, no network needed)
    requirements.txt
    app/, seed_*.py, roaddb.db  previous version (v0) – kept for reference, not used
  frontend/
    src/app/                  React + TypeScript interface
    dist/                     pre-built interface served by the backend
  scripts/process_tools.ps1   process checks used by start/stop
  docs/                       user guide, API reference, screenshots
  runtime/                    created on first start: database, logs, backups, secrets (not in Git)
```

## Documentation

| Document | For |
|---|---|
| [User Guide](road-disruption-intel/docs/USER_GUIDE.md) | Operators – every screen, step by step, with screenshots |
| [Setup Guide](road-disruption-intel/SETUP_GUIDE.md) | Installation, configuration, keys, Ollama, network use, backups |
| [Troubleshooting](road-disruption-intel/TROUBLESHOOTING.md) | Error codes and fixes |
| [Client Handover](road-disruption-intel/CLIENT_HANDOVER.md) | What is verified, limitations, security checklist, go-live assessment |
| [Data Dictionary](road-disruption-intel/DATA_DICTIONARY.md) | Every stored field and status value |
| [API Reference](road-disruption-intel/docs/API.md) | REST API (interactive docs at `/api/docs` while running) |
| [Audit Report](road-disruption-intel/AUDIT_REPORT.md) | Review of the previous version and fixes |
| [Test Report](road-disruption-intel/TEST_REPORT.md) | Automated and manual test results |
| [Changelog](road-disruption-intel/CHANGELOG.md) | Version history |
| [ML Integration Guide (PDF)](road-disruption-intel/docs/ML_INTEGRATION_GUIDE.pdf) | ML team – what, where and how to add machine learning to this repo |

## For developers

```bash
# backend tests (from road-disruption-intel/backend)
..\.venv\Scripts\python -m pytest tests -q

# run the API with auto-reload
..\.venv\Scripts\python -m uvicorn rdi.main:create_app --factory --reload --port 8000

# frontend (from road-disruption-intel/frontend)
npm ci
npm run dev      # http://127.0.0.1:5173, proxies /api to port 8000
npm run build    # writes frontend/dist, served by the backend
```

Stack: Python 3.11+, FastAPI, SQLAlchemy 2 (SQLite, WAL), httpx, feedparser · React 18, TypeScript, Vite,
MapLibre GL (OpenFreeMap basemap) · Ollama / OpenAI-compatible / Anthropic via HTTP.

## Status and limitations

* **Ready for local demonstration; ready for a controlled pilot** with operators reviewing every record.
  **Not production-ready** (no user accounts/HTTPS, accuracy not yet measured on labelled data).
* Most historical records contain only a headline, so severity and exact times are often unknown.
* Locations are approximate; many records name no recognisable place.
* Small local models make mistakes – the review workflow is essential.

See [CLIENT_HANDOVER.md](road-disruption-intel/CLIENT_HANDOVER.md) for the full assessment.

---
© Aviral Consulting (OPC) Private Limited. Map data © OpenStreetMap contributors; basemap by OpenFreeMap.
News content belongs to the respective publishers; the historical data contains headlines and links only.
