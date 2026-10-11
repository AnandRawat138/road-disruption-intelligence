# User guide – Road Disruption Intelligence

A step-by-step guide for operators. No technical knowledge is needed. Screenshots were taken from the running
application with real data on 11 October 2026.

**Contents**
1. [Starting and stopping](#1-starting-and-stopping)
2. [The screen layout](#2-the-screen-layout)
3. [Overview dashboard](#3-overview-dashboard)
4. [First-time setup checklist](#4-first-time-setup-checklist)
5. [Importing data](#5-importing-data)
6. [Setting up the AI model (LLM)](#6-setting-up-the-ai-model-llm)
7. [Getting current news (sources)](#7-getting-current-news-sources)
8. [Classifying records](#8-classifying-records)
9. [Reviewing records (classification queue)](#9-reviewing-records-classification-queue)
10. [Working with a record](#10-working-with-a-record)
11. [Disruptions (incidents)](#11-disruptions-incidents)
12. [Interactive map](#12-interactive-map)
13. [Searching and exporting](#13-searching-and-exporting)
14. [Reports and data quality](#14-reports-and-data-quality)
15. [Alerts](#15-alerts)
16. [Settings, API keys, health and backups](#16-settings-api-keys-health-and-backups)
17. [Using it on a phone or tablet](#17-using-it-on-a-phone-or-tablet)
18. [Glossary](#18-glossary)

---

## 1. Starting and stopping

| Action | How |
|---|---|
| First time | Double-click **`setup_and_start.bat`** in the `road-disruption-intel` folder (see the [installation steps](../../README.md#installation)) |
| Every day | Double-click **`start.bat`**. Your browser opens at **http://127.0.0.1:8000/** |
| Open it again later | Just visit http://127.0.0.1:8000/ (or run `start.bat`, which only opens the browser if it is already running) |
| Stop | Double-click **`stop.bat`** |

The application keeps running in a small minimised window called **“RDI Backend”** even if you close the browser.

## 2. The screen layout

![Screen layout](screenshots/01-overview.png)

* **Left sidebar** – all pages, grouped as *Monitor*, *Work* and *Configure*. Numbers next to *Classification
  queue* and *Alerts* show how many items are waiting.
* **Top bar** – the page title, the alerts bell and the **Operator** box.
* **Operator box (top right)** – type your name once. It is stored in your browser and written into the audit
  trail next to every change you make (approvals, corrections, status changes). It is not a password.

## 3. Overview dashboard

The Overview is the start page. Every number is counted live from the database and refreshes every 30 seconds.
Hover over the ⓘ icon next to a figure to see exactly what it means. **Click any figure** to open the matching list.

| Tile | Meaning |
|---|---|
| Source records | Every row received from files or sources, including repeats of the same article |
| Unique articles | Distinct articles after removing duplicates |
| Relevant reports | Articles the AI classified as real road disruptions |
| Unclassified | Articles not yet analysed by the AI |
| Awaiting review | Classified articles waiting for an operator decision |
| Active incidents | Open incidents with a news report in the last 72 hours |
| High-severity active | Active incidents rated High or Critical |
| Open but stale | Open incidents with **no** recent report – treat as unverified, not as current |
| Resolved (7 days) | Incidents marked resolved in the last week |
| Last live refresh | When a news source was last fetched successfully |

Use the filter bar (dates, state, category) to narrow the charts and counts.

Scroll down for the charts, source health and recent activity:

![Charts and activity](screenshots/02-overview-charts.png)

Click a bar (for example *Diversion* or *Maharashtra*) to open those records.

## 4. First-time setup checklist

The **Getting started** box on the Overview shows five steps. Each tick is set automatically when the step is
really done:

1. Import historical data → section 5
2. Configure and test the LLM → section 6
3. Classify records → section 8
4. Fetch current news from a source → section 7
5. Review and approve records → section 9

Press **Hide** when you no longer need it.

## 5. Importing data

Sidebar → **Data import**.

![Data import](screenshots/12-data-import.png)

1. The table lists every file found in the `data` folder with its role, number of rows and when it was last
   imported.
2. Tick the files you want and press **Import selected**, or press **Import all data files**.
3. A progress bar appears. You can keep working while it runs.
4. When finished, **Import history** shows the real counts:
   * *Discovered* – rows read; *Imported* – new articles; *Duplicate* – already in the database (nothing is lost);
     *Invalid / Failed* – rejected rows; *Skipped* – not processed (e.g. cancelled).
5. If rows were rejected, press the **Errors** button to download a CSV with the line number and reason for each.

**Upload a file:** choose a `.jsonl`, `.json` or `.csv` file under *Upload a file* and press **Upload & import**.
Each row needs at least a title and a URL (or an id or date).

Importing the same file again is safe – it only adds what is new. Original files are never changed.

## 6. Setting up the AI model (LLM)

Sidebar → **LLM configuration**.

![LLM configuration](screenshots/13-llm-config.png)

### Option A – Local model (Ollama, recommended to start)
1. Under **Local LLM setup (Ollama)** check that Ollama shows *Installed* and *Service running*. If not, run
   `setup_llm.bat` or follow the link to the official installer.
2. The table recommends a model for your computer. Press **Download** next to it and confirm (several GB; needs
   internet). Already-installed models show *Installed*.

![Ollama setup](screenshots/14-llm-ollama-setup.png)

3. In **Local Ollama**, type the model name (e.g. `llama3:8b`), press **Save configuration**, then **Test
   connection**. A green *Connected* message means it works.

### Option B – Your own cloud key (OpenAI-compatible or Anthropic)
1. In the provider card, set the API base URL and model name.
2. Paste your key into the key box and press **Save key**. The key is stored on this computer only and is never
   shown again.
3. Choose this provider under **Active provider**, press **Save configuration**, then **Test connection**.
   Cloud usage is billed by the provider.

### Try it
At the bottom, **Test classification** sends a clearly-labelled test headline to the model and shows the
structured result and any validation notes. Nothing is saved.

> The model is never switched automatically. If it fails, you see the error and can retry with another
> provider from a record (section 10).

## 7. Getting current news (sources)

Sidebar → **Sources & acquisition**.

![Sources](screenshots/11-sources.png)

Each card shows:
* **Configuration** – *Configured* or *NOT CONFIGURED* (missing key or feed URL).
* **Verification** – *VERIFIED* only after a real successful fetch on this computer; *FAILING* or *UNVERIFIED* otherwise.
* Last success/attempt, next scheduled run, totals, and the last error in plain language.

Buttons:
* **Fetch now** – fetch immediately (runs in the background; progress is shown).
* **Connection test** – fetch up to 3 sample items without saving them.
* **Settings & history** – change search terms, places, polling interval (minimum 30 minutes), limits, timeouts and
  retries, and see past runs.
* **Scheduled polling** (top-right tick box) – turn automatic fetching on or off for that source.

Google News works without a key. NewsAPI, GNews and Reddit need keys (section 16). Official/custom RSS feeds need
you to paste feed URLs in *Settings & history*.

## 8. Classifying records

Classification means the AI reads an article and records relevance, category, location, road, time, severity and
supporting evidence.

Sidebar → **News & records**.

![Records](screenshots/07-records.png)

* **Some records:** tick them and press **Classify selected**.
* **Many records:** set filters first (for example *Pre-filter: Likely relevant*, *Classification: Unclassified*,
  a date range), enter a maximum in **Classify all matching (max …)** and press **Start**. Confirm the dialog.
* A progress bar shows how many are done. You can cancel at any time.
* Records already classified with the same model and prompt are skipped automatically.

Tip: start with recent records that the keyword *pre-filter* marks as **Likely relevant**. A local model needs
roughly 10–20 seconds per record.

The setting **Automatically classify newly fetched records** (section 16) classifies new news as it arrives.

## 9. Reviewing records (classification queue)

Sidebar → **Classification queue** shows classified records awaiting an operator decision.

![Classification queue](screenshots/10-review-queue.png)

1. Tick **Flagged only** to see records the system thinks need attention first (low confidence, evidence not
   found in the article, unknown location, date problems, old “ongoing” reports).
2. Click a row to open it (section 10), read the original headline and evidence, then decide.
3. For several obvious records at once, tick them and use **Approve** or **Reject** in the action bar
   (rejection asks for confirmation).

What the decisions do:
* **Approve** – confirms the record. Its incident becomes **Confirmed** and is marked as verified by you.
* **Reject** – keeps the record for the audit trail but removes it from incident evidence. An incident left with
  no evidence is dismissed.
* You can change a decision later.

## 10. Working with a record

Click any row in *News & records* or the *Classification queue*.

![Record detail](screenshots/08-record-detail.png)

The panel shows, from top to bottom:
* Status badges, category and severity, and **Open source** (the original article).
* Where it came from: source, publish and retrieval times, the search query that found it, and its linked incident.
* **Original text** – exactly what the source provided (often only the headline).
* **Classification** – relevance, summary, location, road, event time, map position (always marked as
  approximate unless placed by a person), the model’s own confidence, validation result and which model produced it.
* **Supporting excerpt** – the sentence the model relied on, and whether it was found in the article.

Scroll down for actions and history:

![Record actions](screenshots/09-record-detail-actions.png)

* **Review note** + **Approve** / **Reject**.
* **Edit fields** – correct anything (category, city, road, times, severity…). Saving creates a new *human*
  version; the model’s output stays in the history. Enter latitude/longitude to place it exactly on the map.
* **Reclassify** – run the AI again, optionally with a different provider (e.g. after the main one failed).
* **Classification history** – every attempt, including failures, with **Raw output** for checking.
* **Provenance** – every file/query/fetch in which this article appeared.
* **Audit trail** – who changed what and when.

## 11. Disruptions (incidents)

An incident groups reports about the same real-world event. Sidebar → **Disruptions**.

![Disruptions](screenshots/03-disruptions.png)

* Use **All / Active / Open but stale / All open / Resolved** at the top, plus search and filters.
* A **Stale** badge means no new report recently – do not treat it as a current closure without checking.
* A **Conflict** badge means sources disagree (e.g. on severity or timing).

Click an incident to open it:

![Incident detail](screenshots/04-incident-detail.png)

* **Status buttons** move it through *New → Monitoring → Confirmed → Resolved* (or *Dismissed*). Add a note – it is
  saved in the history. Dismissing and resolving ask for confirmation and can be reversed.
* **Linked articles** – evidence with excerpts and source links. **Detach** removes a wrongly-linked article (the
  article is kept).
* **Merge into another incident** – if two incidents are the same event, enter the other incident’s id
  (`INC_…`) and confirm. Articles are moved; nothing is deleted.
* **History** – every status change with who and when.

## 12. Interactive map

Sidebar → **Interactive map**.

![Map](screenshots/05-map.png)

* **Left panel:** the same filters as *Disruptions* (lifecycle, category, severity, status, city, state, highway,
  source, review state), quick time buttons (**7 d / 30 d / 90 d / All**) or exact dates. The list underneath always
  matches what the map shows. It also tells you how many incidents have **no usable location** (they are listed but
  not drawn).
* **Markers:** colour = severity (light = low, dark = critical, grey = unknown); letters = category (e.g. *AC*
  accident, *CL* closure, *DV* diversion, *FL* flooding); dark outline = confirmed; faded = stale; a soft halo = the
  position is only a city centre. Numbers in dark circles are clusters – click to zoom in.
* **Toolbar:** **Fit to results** zooms to all shown incidents; **Reset view** returns to India; **Focus region**
  jumps to Mumbai, Delhi NCR, Pune, etc.
* **Legend** (bottom left) explains the symbols; click it to collapse.

Click a marker or a list item to open the incident panel with evidence and source links:

![Map selection](screenshots/06-map-selected.png)

Press **Open full details** to manage the incident (section 11).

> Positions are approximate (city or locality centres). The map does not show exact closure points or routed road
> segments. The background map needs internet; without it the list still works.

## 13. Searching and exporting

In **News & records**:
* **Search** finds words in titles, summaries, places, roads and sources. Highway searches like `NH 48` or `NH-48`
  also work.
* Combine **Category, Severity, Relevance, Classification, Review, Pre-filter, State, City, Highway, Source,
  dates** and **Flagged only**. The active filter count is shown on **Clear**.
* Click a column heading to sort; use the arrows at the bottom to page through results.
* The page address contains your filters – bookmark it or send it to a colleague on the same computer.

**Export:** press **Export CSV** or **Export JSON** (top right). The file contains exactly the filtered records
(up to 50,000), with a note of when it was generated and which filters were used. *Disruptions* has the same
**CSV / JSON** buttons for incidents. CSV files open directly in Excel.

## 14. Reports and data quality

Sidebar → **Analytics & reports**.

**Summary report** – choose a date range (and optionally a state) and press **Generate**:

![Summary report](screenshots/15-reports.png)

Press **Print / save as PDF** and choose *Save as PDF* in the print dialog to share it.

**Data quality** tab – missing fields, location precision, conflicting and stale incidents, failed
classifications (with a link to retry them), possible duplicate incidents, and source reliability measured from
your own review decisions:

![Data quality](screenshots/16-data-quality.png)

## 15. Alerts

When an incident matching the alert rule (by default: severity **High** or above becoming **Confirmed**) occurs, an
alert appears. The bell in the top bar and the sidebar show the unread count.

![Alerts](screenshots/19-alerts.png)

Click the message to open the incident; use **Mark read** or **Mark all read**. Each incident raises at most one
alert per rule. Alerts are in-app only (no e-mail/SMS).

## 16. Settings, API keys, health and backups

Sidebar → **Settings & health**.

![Settings](screenshots/17-settings.png)

* **Branding & workflow** – company and product name, optional logo URL; classification rules (auto-classify, what
  gets flagged); incident rules (stale after N hours, linking window, auto-resolve); alert rules; map style.
  Press **Save** on each card.
* **API keys** – enter or remove keys for news sources and AI providers. Keys are stored only on this computer and
  are never shown again.
* **Health & backups** – system checks, where data is stored, what needs internet, and **Back up now**:

![Health and backups](screenshots/18-health-backups.png)

* **Audit trail** – every recorded change, newest first.

Restoring a backup is described in [SETUP_GUIDE.md](../SETUP_GUIDE.md#10-backups-and-restore).

## 17. Using it on a phone or tablet

The interface adapts to small screens. Use the ☰ button (top left) to open the menu. On the map page, tap
**Filters** to show or hide the filters.

| Overview | Map |
|---|---|
| ![Mobile overview](screenshots/20-mobile-overview.png) | ![Mobile map](screenshots/21-mobile-map.png) |

By default the application only accepts connections from the computer it runs on. To use it from other devices on
your office network, see [SETUP_GUIDE.md §9](../SETUP_GUIDE.md#9-using-it-from-other-computers-optional).

## 18. Glossary

| Term | Meaning |
|---|---|
| Record / article | One news item from a file or source |
| Pre-filter | A quick keyword check used only to decide what to classify first – not an AI decision |
| Classification | The AI’s structured reading of a record (relevance, category, location, time, severity, evidence) |
| Relevant / Related / Irrelevant | A real road disruption / general transport news / not about roads in India |
| Incident | A group of records about the same event |
| Active | Open incident with a recent report (default 72 h) |
| Stale | Open incident with no recent report – not verified as current |
| Approximate location | City or locality centre, not the exact spot |
| Model confidence | The AI’s own judgement (Low/Medium/High), not a measured probability |
| Provenance | Where and when a record was seen |
| Audit trail | Log of who changed what and when |
