# Setup guide

This guide is for the person installing and running the application on a Windows PC. No programming
knowledge is required.

## 1. Requirements

| Item | Needed? | Notes |
|---|---|---|
| Windows 10 (1803+) or Windows 11 | Yes | Uses the built-in `curl.exe` and PowerShell |
| Python 3.11, 3.12, 3.13 or 3.14 | Yes | [python.org/downloads/windows](https://www.python.org/downloads/windows/) – tick *Add python.exe to PATH* |
| Internet connection | First setup | To install Python packages; afterwards for live news, geocoding and map tiles |
| Node.js | No | Only if you change the interface source and run `setup_and_start.bat --rebuild-ui` |
| Ollama | Optional | For local AI classification – see section 6 |
| GPU | Optional | Speeds up local models; not required |
| Administrator rights | No | Everything installs inside the project folder |

Disk space: about 300 MB for the application and database, plus 2–9 GB per local AI model.

## 2. Folder layout

Keep the historical data folder next to the project (as delivered):

```
Road_project\
  data\                     ← historical files (read-only)
  road-disruption-intel\    ← the application (run the .bat files here)
```

The application also finds a `data` folder *inside* `road-disruption-intel`. Another location can be set
with `HISTORICAL_DATA_DIR` in `.env`. Paths with spaces are supported.

## 3. First start

Double-click `setup_and_start.bat`. It runs seven numbered stages and stops with an explanation if anything
fails (it never closes silently):

1. Find Python 3.11+.
2. Create `.venv` (a private Python environment in the project folder).
3. Install backend packages – only when missing or when `requirements.txt` changed.
4. Check the pre-built web interface (`frontend\dist`).
5. Create `.env` from `.env.example` **only if `.env` does not exist** (it is never overwritten) and
   create/upgrade the database (a backup is made before any upgrade).
6. List the historical data files and, if nothing was imported yet, ask whether to import them now
   (≈ 2–4 minutes for the delivered 78,000 rows).
7. Report whether a local Ollama service is available.

It then calls `start.bat`, waits until the server answers and opens **http://127.0.0.1:8000/**.

Re-running `setup_and_start.bat` is safe – it skips everything already done.

## 4. Daily use

* Start: `start.bat` (opens the browser; if the app is already running it just opens the browser).
* Stop: `stop.bat` (graceful shutdown; only this application’s process is touched).
* Logs: `runtime\logs\server.log` (console) and `runtime\logs\backend.jsonl` (structured).
* Enter your name in the **Operator** box at the top right – it is recorded in the audit trail.

The server keeps running after you close the browser. Close it with `stop.bat` (or by closing the
minimised “RDI Backend” window).

## 5. Configuration (`.env`)

Open `.env` in Notepad. All settings are optional:

| Setting | Default | Meaning |
|---|---|---|
| `APP_PORT` | 8000 | Change if another program uses port 8000 |
| `APP_HOST` | 127.0.0.1 | Keep for single-PC use |
| `APP_ALLOW_REMOTE`, `APP_ACCESS_TOKEN` | off | Both required to serve other computers (see section 9) |
| `HISTORICAL_DATA_DIR` | auto | Location of the `data` folder |
| `SCHEDULER_ENABLED` | true | Automatic polling of enabled sources |
| `GEOCODING_ONLINE` | true | Use OpenStreetMap Nominatim for localities; `false` = offline city/state table only |
| `NOMINATIM_CONTACT_EMAIL` | empty | Recommended by Nominatim’s usage policy |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `NEWSAPI_KEY`, `GNEWS_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | empty | Optional keys (can also be entered in the UI) |

Restart (`stop.bat`, then `start.bat`) after editing `.env`.

## 6. Local AI with Ollama (optional)

Run `setup_llm.bat`. It:

1. Detects whether Ollama is installed and running (it never reinstalls an existing copy).
2. If missing, explains that installation needs the internet and offers to open the **official** download
   page (`https://ollama.com/download/windows`). The installer needs you to click through it.
3. Checks RAM, GPU memory and free disk space and recommends a model.
4. Lets you choose a model and **downloads only after you type `y`**.
5. Runs a small test and, if you agree, makes the model the active classifier.

Approximate requirements (4-bit models):

| Model | Download | RAM | Notes |
|---|---|---|---|
| `llama3.2:3b` | 2 GB | 8 GB | Fast, weaker extraction |
| `qwen2.5:7b` | 4.7 GB | 12 GB | Recommended for 16 GB PCs |
| `llama3:8b` | 4.7 GB | 12 GB | Tested with this application |
| `qwen2.5:14b` | 9 GB | 24 GB | Better quality; slow without a 10 GB+ GPU |

The same steps are available in the web UI under **LLM configuration → Local LLM setup**.

## 7. Cloud AI with your own key (optional)

**LLM configuration** → choose *OpenAI / OpenAI-compatible* or *Anthropic* → set base URL and model →
paste the key → **Save key** → **Save configuration** → **Test connection**.

Where keys are stored: in `runtime\secrets.json` on this PC (plain JSON, protected by Windows file
permissions, **not encrypted**), or in `.env`/environment variables, which take precedence. Keys are never
shown again, never sent to the browser and are redacted from logs. **Remove** deletes a key from
`secrets.json`. Cloud usage is billed by the provider.

## 8. Importing data

**Data import** lists the files in the historical data folder with their role, row count and last import.
Select files and press **Import selected**, or **Import all data files**. You can also upload a JSONL,
JSON-array or CSV file. Import is idempotent: re-importing the same file adds no duplicates. Rejected rows
are listed in a downloadable CSV error report. Source files are never modified.

## 9. Using it from other computers (optional)

Not needed for a single PC. To allow access over a trusted office network:

```
APP_HOST=0.0.0.0
APP_ALLOW_REMOTE=true
APP_ACCESS_TOKEN=<a long random string, 16+ characters>
```

Users then sign in with that token. The application uses plain HTTP; for anything beyond a trusted LAN put it
behind an HTTPS reverse proxy. Without both settings the server refuses to listen on the network.

## 10. Backups and restore

* Automatic: before any database upgrade, into `runtime\backups`.
* Manual: **Settings & health → Health & backups → Back up now**, or
  `.venv\Scripts\python -m rdi.cli backup` from the `backend` folder.
* Restore: run `stop.bat`, then from the `backend` folder:
  `..\.venv\Scripts\python -m rdi.cli restore rdi_YYYYMMDD_HHMMSS_manual.db --yes`
  (the current database is saved first), then `start.bat`.

Copy the whole `runtime` folder to another drive for an off-machine backup (it contains `secrets.json` –
store it securely).

## 11. Updating the interface (developers)

```
cd frontend
npm ci
npm run build
```

or run `setup_and_start.bat --rebuild-ui`. For live development: `npm run dev` (port 5173, proxies `/api`
to port 8000).
