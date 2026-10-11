# Temporal-Geospatial Road Disruption Intelligence
## Research Novelty & Academic Value

This project elevates traditional traffic-monitoring web scrapers into a **research-grade Temporal-Geospatial intelligence system** by combining advanced Natural Language Processing (NLP) with dynamic graph theory.

### 1. Zero-Shot Spatiotemporal Extraction (Llama 3)
Traditional traffic parsers rely on rigid Regex or static Named Entity Recognition (NER). This system utilizes a localized Large Language Model (Llama 3 8B) running via `langchain_ollama` to perform strict Pydantic JSON extraction. It captures abstract temporal semantics (e.g., "until the monsoon recedes" or "for the next 48 hours") and translates them into hard DateTime bounding boxes, assigning an explicit **Temporal Confidence Score**.

### 2. Temporal Normalization & Open-Ended Logic
Disruptions without explicit end dates are logically handled using an `OPEN_ENDED` status. The system applies dynamic degradation to their risk scores over time if no supporting evidence is ingested, mitigating the "zombie data" problem common in static datasets (e.g., road closures from 2 years ago remaining active on Google Maps).

### 3. Multisource Evidence Fusion Engine
The system does not treat news articles as absolute truth. Instead, it utilizes an Evidence Fusion algorithm:
*   It clusters similar events based on Levenshtein/Jaccard topological similarity and overlapping Temporal Bounding Boxes.
*   It aggressively penalizes duplicated syndicate sources (e.g., wire articles republished by 5 different local outlets).
*   It computes a unified `road_risk_score` weighting the raw severity, semantic certainty of the AI, and chronological relevance.

### 4. Time-Sliced Topological Routing ($G_t$)
Routing engines like OSRM or Google Maps base routes on static map data with minor traffic overlays. This engine generates a Time-Sliced Graph $G_t$, explicitly mapping the `start_time` and `end_time` of a disruption. 
When a route is requested with a `departure_time`:
1.  The system pulls the specific temporal disruptions overlapping that exact window.
2.  It intersects the geographical paths of the road geometries.
3.  It scales the network edge traversal weights ($\Delta W$) dynamically based on the NLP-derived Impact Multiplier (e.g., `FULL_CLOSURE = 1000x`, `PARTIAL_CLOSURE = 3x`).
4.  It instantly routes a topological bypass if an intersection occurs, providing highly accurate predictive detours.

### 5. Automated Data Generation Loop
The pipeline continuously structures chaotic, unstructured web text into a clean, normalized `ml_dataset.jsonl` (Version 2.0). This dataset includes explicit ablation flags and geometric bounds, designed to be fed into downstream deep-learning models (like Graph Neural Networks) to predict traffic flow ripple effects.
