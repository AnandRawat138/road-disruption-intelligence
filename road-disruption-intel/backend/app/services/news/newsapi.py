import requests
from typing import List, Dict
from app.services.news.base import NewsProvider
from app.config import settings
from datetime import datetime

class NewsAPIProvider(NewsProvider):
    def __init__(self):
        self.api_key = settings.NEWSAPI_KEY
        self.base_url = "https://newsapi.org/v2/everything"
        
    def fetch_news(self, query: str) -> List[Dict]:
        if not self.api_key:
            print("NewsAPI Key missing, using mock data")
            return self._mock_data()
            
        params = {
            "q": query,
            "apiKey": self.api_key,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 20
        }
        
        try:
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            articles = []
            for item in data.get('articles', []):
                published_str = item.get('publishedAt')
                pub_date = None
                if published_str:
                    pub_date = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                    
                articles.append({
                    "title": item.get('title'),
                    "description": item.get('description'),
                    "content": item.get('content'),
                    "source_name": item.get('source', {}).get('name'),
                    "source_url": item.get('url'),
                    "published_at": pub_date
                })
            return articles
        except Exception as e:
            print(f"NewsAPI error: {e}")
            return self._mock_data()

    def _mock_data(self) -> List[Dict]:
        """Synthetic data if API fails or key is missing."""
        return [
            {
                "title": "[DEMO] NH-19 Blocked near Varanasi due to Religious Procession",
                "description": "Heavy traffic jam reported on NH-19 near Varanasi as thousands gather for the religious procession.",
                "content": "Traffic movement on NH-19 will remain restricted from 10 AM to 3 PM tomorrow due to a religious procession. Heavy vehicles are being diverted via Mirzapur.",
                "source_name": "Demo News",
                "source_url": "http://demo-news.local/1",
                "published_at": datetime.utcnow()
            },
            {
                "title": "[DEMO] Flooding on NH-27 in Nagaon, Assam",
                "description": "Continuous rains have led to severe waterlogging on NH-27, halting commercial freight.",
                "content": "The SDMA has issued an advisory stating NH-27 in Nagaon is completely submerged. Through traffic is suspended until water recedes.",
                "source_name": "Demo News",
                "source_url": "http://demo-news.local/2",
                "published_at": datetime.utcnow()
            }
        ]
