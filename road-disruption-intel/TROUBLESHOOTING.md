# Troubleshooting

Start with **`diagnose.bat`** – it checks Python, the database, the port, Ollama and internet access
without changing anything. Logs are in `runtime\logs\` (`setup.log`, `server.log`, `backend.jsonl`).

## Setup and start

| Symptom / error code | Cause | Fix |
|---|---|---|
| `[ERROR] Python 3.11 or newer was not found` (code 11) | Python missing or not on PATH | Install from python.org with *Add python.exe to PATH*, open a new window, re-run |
| Code 12 – cannot create virtual environment | Folder not writable / antivirus | Move the project to a folder you own (e.g. `D:\RoadIntel`), re-run |
| Code 13 – package installation failed | No internet, proxy, firewall | Check `runtime\logs\setup.log`; set `HTTPS_PROXY` if your office uses a proxy; re-run |
| Code 14 – Node.js not found | `frontend\dist` missing | Restore `frontend\dist` from the delivery, or install Node.js LTS |
| Code 16 – database initialisation failed | Disk full / permissions / damaged DB | See `backend.jsonl`; restore a backup (SETUP_GUIDE §10) |
| Code 20 – port already used | Another program or another copy uses port 8000 | Stop it, or set `APP_PORT=8010` in `.env` |
| Code 30 – backend not ready in 90 s | Error at startup | `start.bat` prints the last 25 log lines; see `server.log` |
| Browser shows “web interface has not been built” | `frontend\dist` missing | See code 14 |
| `stop.bat` says “not running” but the page still loads | A different copy/folder is running | Run `stop.bat` in that copy’s folder |

## Data import

* **Everything counted as “duplicate”** – the file was already imported. This is expected; nothing is lost.
* **Rows marked invalid** – download the error CSV from *Data import → Import history*. Common reasons:
  missing title, invalid URL (`javascript:` etc.), no URL/id/date, malformed JSON line, implausible date.
* **Import shows INTERRUPTED** – the app was stopped during the import. Run it again; it is idempotent.

## Sources

| Status | Meaning | What to do |
|---|---|---|
| `NOT CONFIGURED` | Key or feed URL missing | Add the key under *Settings & health → API keys* |
| `AUTH_FAILED` | Provider rejected the key (401/403) | Check the key / plan; the source is retried only once a day |
| `RATE_LIMITED` | HTTP 429 from the provider | Increase the polling interval. GDELT allows ~1 request per 5 s per client and rejected every request from the development network – it may work from another network |
| `PARTIAL` | Some queries failed | See *Last error*; other queries were stored |
| `ERROR` | Network or parse error | Check internet; *Connection test* shows the exact message |
| Verification `UNVERIFIED` | Never fetched successfully on this PC | Press *Fetch now* or *Connection test* |

Each source runs independently; one failing source never stops the others.

## Language model

| Message | Fix |
|---|---|
| `ollama: cannot connect to http://127.0.0.1:11434` | Start “Ollama” from the Start menu, or run `setup_llm.bat` |
| `model 'x' is not installed` | Run `setup_llm.bat` or `ollama pull x`, or pick an installed model |
| `authentication failed (HTTP 401)` | Wrong or expired API key – replace it on the LLM page |
| `rate limited or quota exceeded (HTTP 429)` | Provider limit/billing – wait or check your plan |
| `request timed out` | Model too large for the PC – choose a smaller model or raise the timeout |
| Job “Stopped after 10 consecutive failures” | Provider is down/misconfigured – fix it, then re-run; failed records keep their history |
| Many records classified OTHER/UNKNOWN | Small local models are less accurate. Use a larger model or a cloud provider and **Reclassify** |

A failing provider is never replaced automatically. Use *Reclassify* in the record panel with another
provider, or change the active provider.

## Map

* **Grey map with a warning** – the basemap needs internet. Incidents are still listed on the left.
  Another MapLibre style URL can be set in *Settings → Map*.
* **“N without a usable location”** – the article named no recognisable city/locality. Open the record and
  set the city, or enter manual coordinates.
* **Points look misplaced** – positions are city/locality centroids (approximate). Correct them manually in
  the record panel; manual positions are marked “Operator-placed”.

## Database maintenance

* Backup / restore: SETUP_GUIDE §10.
* `database is locked` in logs during very heavy use: transient; operations retry for 30 s.
* Re-compute keyword pre-filter labels after a software update: from `backend`,
  `..\.venv\Scripts\python -m rdi.cli refresh-prefilter`.
