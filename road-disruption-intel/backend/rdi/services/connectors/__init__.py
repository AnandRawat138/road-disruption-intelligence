from .apis import GDELTConnector, GNewsConnector, NewsAPIConnector, RedditConnector
from .base import Connector, ConnectorError, FetchResult
from .feeds import CustomRSSConnector, GoogleNewsRSSConnector

CONNECTORS: dict[str, type[Connector]] = {
    c.type_id: c for c in (GoogleNewsRSSConnector, GDELTConnector, NewsAPIConnector, GNewsConnector,
                           RedditConnector, CustomRSSConnector)
}

# Sources created on first start. Only the verified, key-free Google News feed is enabled by default.
DEFAULT_SOURCES = [
    {"id": "google_news_india", "name": "Google News – India road disruptions", "connector_type": "google_news_rss",
     "enabled": True, "poll_interval_minutes": 180, "max_records": 300},
    {"id": "gdelt_india", "name": "GDELT – India", "connector_type": "gdelt_doc", "enabled": False,
     "poll_interval_minutes": 360, "max_records": 150},
    {"id": "newsapi", "name": "NewsAPI.org", "connector_type": "newsapi", "enabled": False,
     "poll_interval_minutes": 360, "max_records": 100},
    {"id": "gnews", "name": "GNews.io", "connector_type": "gnews", "enabled": False,
     "poll_interval_minutes": 360, "max_records": 50},
    {"id": "reddit", "name": "Reddit city communities", "connector_type": "reddit", "enabled": False,
     "poll_interval_minutes": 240, "max_records": 100},
    {"id": "official_feeds", "name": "Official / custom RSS feeds", "connector_type": "custom_rss", "enabled": False,
     "poll_interval_minutes": 120, "max_records": 200},
]

__all__ = ["CONNECTORS", "DEFAULT_SOURCES", "Connector", "ConnectorError", "FetchResult"]
