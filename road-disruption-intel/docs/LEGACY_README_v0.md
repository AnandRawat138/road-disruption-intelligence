# AI-Powered Indian Highway Disruption Intelligence System

A full-stack, AI-powered platform for continuously monitoring, extracting, evaluating, and visualizing road and freight disruptions across India using multi-source NLP.

## 1. Architecture Overview
This system implements the **Multisource Temporal-Geospatial Evidence Fusion** framework:
*   **Ingestion (Celery/Redis)**: Periodically fetches unstructured news from APIs/RSS.
*   **NLP/AI Layer (FastAPI/LangChain/Ollama)**: Evaluates semantic relevance before utilizing a strictly structured local LLM (e.g. Llama3) to extract specific road/event intelligence.
*   **Geospatial (Nominatim/OSMnx/PostGIS)**: Translates local Indian text entities into lat/lon bounding boxes and snaps them to the nearest major freight highway on OpenStreetMap.
*   **Evidence Fusion Engine**: Deduplicates reports matching geographical and temporal vectors, scoring confidence dynamically based on source reliability (e.g., NHAI vs local news) and contradiction absence.
*   **Routing**: Calculates shortest-paths via NetworkX, scaling the weights (travel cost) of disrupted highway segments based on the severity and confidence parameters.
*   **Dashboard (React/MapLibre)**: An interactive frontend presenting active freight closures dynamically.

## 2. Files Created
*   `docker-compose.yml`: Entire stack orchestration.
*   `backend/app/main.py`: FastAPI server entrypoint.
*   `backend/app/models/*.py`: PostGIS-ready SQLAlchemy models (Article, Event, Road, Disruption, Evidence).
*   `backend/app/schemas/*.py`: Pydantic validations for LLM output.
*   `backend/app/workers/*.py`: Celery pipelines for background scraping and NLP execution.
*   `backend/app/services/news/newsapi.py`: External NewsAPI integration with synthetic fallback dataset.
*   `backend/app/services/nlp/extraction.py`: LangChain-powered structured LLM data extraction.
*   `backend/app/services/nlp/relevance.py`: Quick heuristic filter to save LLM tokens.
*   `backend/app/services/nlp/temporal.py`: Relative-time NLP parsing (`dateparser`).
*   `backend/app/services/geo/geocoder.py`: India-contextualized Nominatim integration.
*   `backend/app/services/geo/road_matcher.py`: OSMnx dynamic graph mapping.
*   `backend/app/services/evidence/fusion.py` & `confidence.py`: Multisource deduplication and confidence scoring.
*   `backend/app/services/routing/router.py`: Graph-based dynamic edge-cost freight routing.
*   `frontend/*`: Vite-React-MapLibre web dashboard (`App.tsx`, `vite.config.ts`, `package.json`).

## 3 & 4. Installation & API Key Configuration
1. Clone this repository and ensure **Docker** and **Docker Compose** are installed.
2. In the root directory, rename `.env.example` to `.env`.
3. Open `.env` and configure your keys:
   *   `NEWSAPI_KEY`: (Optional) Get one from newsapi.org. If omitted, the system will inject the required **Demo/Synthetic dataset** (Varanasi NH-19, Assam NH-27) automatically!
   *   `OLLAMA_BASE_URL`: Leave as `http://host.docker.internal:11434` if you are running Ollama locally on your host machine.
   *   `OLLAMA_MODEL`: e.g. `llama3`

## 5. Starting the Application
Simply run:
```bash
docker compose up --build
```
This single command spins up:
1. PostgreSQL + PostGIS (`db`)
2. Redis Cache (`redis`)
3. FastAPI Backend (`backend`) at `http://localhost:8000`
4. Celery Background Worker (`worker`)
5. React Dashboard (`frontend`) at `http://localhost:5173`

*(Note: The Celery worker will immediately trigger the first news ingestion task upon boot).*

## 6. Example API Calls
*   **Get Active Disruptions**: `curl http://localhost:8000/api/disruptions/active`
*   **Get Raw Events**: `curl http://localhost:8000/api/events/`
*   **Test Routing**:
    ```bash
    curl -X POST http://localhost:8000/api/routes/ \
      -H "Content-Type: application/json" \
      -d '{"origin": "Delhi", "destination": "Agra"}'
    ```

## 7. Running Tests
To run tests (requires `pytest`):
```bash
docker compose exec backend pytest tests/
```

## 8. Research-Novel Components
*   **Multisource Confidence Matrix**: Instead of trusting a single LLM interpretation, the system groups events by GIS-bounding boxes and temporally overlapping windows, calculating a probabilistic certainty score based on source prestige and text contradictions.
*   **Semantic-To-GIS Bridge**: Direct conversion from unverified NLP output (e.g. "NH-19 near Varanasi") to `osmnx` bounding boxes and finally to a strictly routable edge vector.

## 9. Current Limitations
*   **LLM Hallucinations**: Despite strict Pydantic schemas, local models (if using a very small one like `llama3:8b`) might occasionally fail JSON formatting. The code drops these safely but loses potential data.
*   **Mock Geometry**: In the current MVP, exact `LINESTRING` geometry from OSMnx isn't being deeply serialized to PostGIS to avoid complex Shapely transformations in Docker; they are mocked using coordinate centroids.

## 10. Next Research Phase Recommendations
*   **Automated Evaluation Module (`/evaluation`)**: Build the pipeline to calculate the Brier Score of our confidence matrix against a ground-truth dataset.
*   **Weekly PDF Exporter**: Implement an automated CRON worker utilizing `pdfkit` to compile the active disruption matrix and email it to logistics operators every Monday morning.
*   **Multilingual Expansion**: Integrate Indic language translation (e.g. `Bhashini` API) before the LLM extraction layer to tap into regional Hindi/Marathi transport alerts.
