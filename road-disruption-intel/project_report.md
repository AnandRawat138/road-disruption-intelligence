# Project Report: Road Disruption Intelligence Tool
**Date:** September 9, 2026
**Scope:** AI-Based Indian Highway Transport Disruption Mapping

---

## 1. Executive Summary
The Road Disruption Intelligence Tool is a fully automated, end-to-end system designed to monitor, extract, and map real-time highway closures and traffic disruptions across India. The system continuously ingests unstructured news data, leverages a Local Large Language Model (LLM) to extract structured insights, and plots the affected routes on an interactive dashboard. 

## 2. Current Architecture & Tech Stack (Lite Version)
To eliminate heavy infrastructure requirements (like Docker and PostgreSQL), the tool was built using a lightweight, native stack:
* **Database:** SQLite (`roaddb.db`) with native JSON geometry storage.
* **Backend:** Python FastAPI running native background threads for continuous ingestion.
* **Frontend:** React + Vite, utilizing interactive map rendering for `LineString` geometries.
* **AI/NLP Layer:** Local `langchain_ollama` (Llama3) for entirely free, offline natural language extraction.
* **Geocoding:** Free OSM Nominatim API for translating locations to coordinates.

## 3. Key Features Implemented

### A. Automated Multi-Source Data Ingestion
The system features a robust background worker that continuously queries free APIs (Google News RSS) using an expanded array of Indian-specific traffic terminology (e.g., *"highway cave-in"*, *"traffic curfew"*, *"gridlock"*). It automatically filters out outdated news and deduplicates overlapping articles.

### B. AI-Powered NLP Extraction
Unstructured news text is fed into a locally running Llama3 model. The AI parses the text and strictly outputs a JSON schema containing:
* `event_type` (e.g., FLOODING, ACCIDENT, CONSTRUCTION)
* `impact_type` (e.g., FULL_CLOSURE, TRAFFIC_DIVERSION)
* Geographic markers (Cities, States, Landmarks, Highways)
* Temporal Data (Start and End times)

### C. Automated Evidence Fusion
When multiple news articles report on the same event, the backend automatically fuses them together. It resolves temporal conflicts, merges evidence text, and upgrades the event's "certainty score" based on multi-source verification.

### D. Interactive Mapping Dashboard
The React frontend dynamically fetches active disruptions and renders them as thick road segments on the map. Clicking a segment opens a detailed sidebar displaying the AI-extracted description, timeframes, severity scores, and clickable source citations.

### E. Machine Learning Dataset Generation
For every highly verified event (Certainty >= 0.7), the pipeline automatically logs a highly structured JSONL record to `ml_dataset.jsonl` to build training data for future predictive ML models.

---

## 4. Technical Hurdles & Resolutions
1. **Reddit API Blocking:** Attempted to integrate free Reddit JSON scraping, but Reddit's recent unauthenticated bot-blocking (HTTP 403) prevented access. *Resolution:* Shifted to a massive, multi-query Google News RSS architecture.
2. **Local LLM Batching Bottleneck:** The local Llama3 model takes ~20 seconds per article, causing the UI to appear frozen while large batches processed. *Resolution:* Refactored the processing loop to stream and commit database updates instantly per article.
3. **Timezone Fusion Crashes:** Merging naive SQLite datetimes with timezone-aware NLP datetimes caused pipeline crashes. *Resolution:* Standardized the `TemporalNormalizer` to emit SQLite-compatible naive datetimes.

---

## 5. Future Enhancements (Impact of Paid APIs)
Upgrading the current "Lite/Free" architecture with enterprise paid APIs would drastically scale the system's speed, accuracy, and coverage:

### 1. Paid LLM APIs (OpenAI GPT-4o / Google Gemini Pro)
* **Current Issue:** Local Llama3 takes 20-30 seconds per article, limiting ingestion to a few dozen articles an hour. It also occasionally hallucinates JSON structures.
* **Paid Impact:** Cloud LLMs offer sub-second inference. The system could process **thousands of articles per minute** with near-perfect JSON schema adherence and highly advanced reasoning for complex multi-highway disruptions.

### 2. Premium Data Providers (EventRegistry / NewsAPI / X Enterprise API)
* **Current Issue:** Google News RSS truncates results to the "Top 20" articles and hides highly localized, obscure sources.
* **Paid Impact:** Real-time firehose access to every published article and tweet in India. We could ingest live updates from regional traffic police X (Twitter) accounts, detecting accidents *minutes* after they occur, rather than waiting for formal news coverage.

### 3. Enterprise Routing (Google Maps Directions API)
* **Current Issue:** We currently draw simple bounding boxes and `LineStrings` based on coordinate bounding.
* **Paid Impact:** We could snap the exact disruption coordinates to actual road networks. The UI would perfectly highlight the exact curves of the affected highway, and we could automatically calculate alternate route ETAs based on live traffic congestion overlays.

### 4. Enterprise Database (PostgreSQL + PostGIS)
* **Current Issue:** SQLite cannot perform advanced spatial mathematics.
* **Paid Impact:** PostGIS enables complex geometric queries, such as automatically detecting if two accidents are within a 5km radius on the same highway, drastically improving the Evidence Fusion system.
