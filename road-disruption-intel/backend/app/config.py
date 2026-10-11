import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "")
    GNEWS_API_KEY: str = os.getenv("GNEWS_API_KEY", "")
    
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
    
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./roaddb.db")
    
    GEOCODING_PROVIDER: str = os.getenv("GEOCODING_PROVIDER", "nominatim")
    ROUTING_PROVIDER: str = os.getenv("ROUTING_PROVIDER", "osrm")
    
    CITY_DEFAULT: str = os.getenv("CITY_DEFAULT", "Delhi")
    NEWS_POLL_INTERVAL_MINUTES: int = int(os.getenv("NEWS_POLL_INTERVAL_MINUTES", "30"))
    
    # Research Ablation Toggles (Step 27)
    ENABLE_TEMPORAL_REASONING: bool = os.getenv("ENABLE_TEMPORAL_REASONING", "true").lower() == "true"
    ENABLE_EVIDENCE_FUSION: bool = os.getenv("ENABLE_EVIDENCE_FUSION", "true").lower() == "true"
    ENABLE_GEOGRAPHIC_MATCHING: bool = os.getenv("ENABLE_GEOGRAPHIC_MATCHING", "true").lower() == "true"
    ENABLE_CONTRADICTION_DETECTION: bool = os.getenv("ENABLE_CONTRADICTION_DETECTION", "true").lower() == "true"
    ENABLE_MULTISOURCE: bool = os.getenv("ENABLE_MULTISOURCE", "true").lower() == "true"

settings = Settings()
