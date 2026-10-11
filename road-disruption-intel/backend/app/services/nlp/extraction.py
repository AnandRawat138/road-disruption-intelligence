import json
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from app.config import settings
from app.schemas.event import EventExtractionSchema
from typing import Optional

class EventExtractor:
    def __init__(self):
        # We will use Ollama for local LLM inference
        # Added a strict timeout because the local Ollama server appears to be hanging/frozen
        import httpx
        self.llm = ChatOllama(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
            temperature=0.0,
            format="json",  # Ensure JSON output from Ollama
            client=httpx.AsyncClient(timeout=15.0)
        )
        
        self.prompt = PromptTemplate(
            template="""You are an expert traffic and logistics intelligence AI.
Analyze the following news article and extract road disruption information strictly as a JSON object matching the requested schema.

If there is no actual road disruption, return an empty JSON object {{}}.

Article Title: {title}
Article Content: {content}

JSON Schema Required:
{{
  "event_type": "PROTEST|RALLY|ROAD_SHOW|VIP_MOVEMENT|STRIKE|ACCIDENT|FLOOD|WATERLOGGING|CONSTRUCTION|OTHER",
  "impact_type": "FULL_CLOSURE|PARTIAL_CLOSURE|TRAFFIC_DIVERSION|HEAVY_TRAFFIC|POTENTIAL_BLOCKAGE",
  "event_name": "Name of the event (e.g. Farmers Protest)",
  "description": "Short summary of the disruption",
  "city": "Extracted city",
  "state": "Extracted state (India context)",
  "locations": ["List of areas"],
  "roads": ["List of affected roads/highways, e.g. NH-19, Mall Road"],
  "landmarks": ["List of landmarks"],
  "start_time": "YYYY-MM-DDTHH:MM:SS (if mentioned precision, else null)",
  "end_time": "YYYY-MM-DDTHH:MM:SS (if mentioned precision, else null)",
  "temporal_expression": "Original text mentioning the time (e.g. 'tomorrow morning', 'until further notice', 'from 10 AM to 3 PM')",
  "severity": 0.8,
  "extraction_confidence": 0.9,
  "evidence_text": ["Exact sentences from the article proving the closure"]
}}

Respond ONLY with valid JSON.
""",
            input_variables=["title", "content"]
        )

    def extract(self, title: str, content: str, article_id: str, retries: int = 1) -> Optional[EventExtractionSchema]:
        import traceback
        for attempt in range(retries + 1):
            try:
                chain = self.prompt | self.llm
                response = chain.invoke({"title": title, "content": content})
                
                raw_json = response.content.strip()
                # Simple repair for markdown blocks
                if raw_json.startswith("```json"):
                    raw_json = raw_json[7:]
                if raw_json.startswith("```"):
                    raw_json = raw_json[3:]
                if raw_json.endswith("```"):
                    raw_json = raw_json[:-3]
                    
                response_json = json.loads(raw_json.strip())
                
                if not response_json or "event_type" not in response_json:
                    return None
                    
                response_json["source_article_id"] = str(article_id)
                
                # Validation mapping for old schema keys if LLM hallucinated them
                if "certainty" in response_json and "extraction_confidence" not in response_json:
                    response_json["extraction_confidence"] = response_json.pop("certainty")
                if "duration_text" in response_json and "temporal_expression" not in response_json:
                    response_json["temporal_expression"] = response_json.pop("duration_text")
                    
                # Validate with Pydantic
                validated_event = EventExtractionSchema(**response_json)
                return validated_event
                
            except Exception as e:
                print(f"LLM Extraction failed for article {article_id} (Attempt {attempt+1}): {e}")
                if attempt == retries:
                    # Log full traceback on final failure for debugging
                    traceback.print_exc()
                    return None
        return None
