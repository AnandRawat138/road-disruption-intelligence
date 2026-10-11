from abc import ABC, abstractmethod
from typing import List, Dict

class NewsProvider(ABC):
    @abstractmethod
    def fetch_news(self, query: str) -> List[Dict]:
        """Fetch news and return a list of dictionaries containing article details"""
        pass
