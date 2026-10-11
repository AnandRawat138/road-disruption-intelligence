import feedparser
from typing import List, Dict
from datetime import datetime
from email.utils import parsedate_to_datetime
import urllib.parse
from app.services.news.base import NewsProvider

class GoogleNewsRSSProvider(NewsProvider):
    def fetch_news(self, query: str) -> List[Dict]:
        """
        Fetches news using Google News RSS, strictly limited to the past 7 days.
        """
        # Append when:7d to ensure Google returns recent news
        encoded_query = urllib.parse.quote(query + " when:7d")
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
        
        try:
            feed = feedparser.parse(rss_url)
            articles = []
            
            now = datetime.utcnow()
            
            for entry in feed.entries[:20]:
                pub_date = None
                if hasattr(entry, 'published'):
                    try:
                        pub_date = parsedate_to_datetime(entry.published)
                        # Remove timezone info for simple comparison
                        pub_date = pub_date.replace(tzinfo=None)
                    except Exception:
                        pass
                
                # STRICT FILTER: Reject articles older than 7 days
                if pub_date and (now - pub_date).days > 7:
                    continue
                    
                source_name = getattr(entry, 'source', {}).get('title', 'Google News')
                
                articles.append({
                    "title": entry.title,
                    "description": getattr(entry, 'description', ''),
                    "content": getattr(entry, 'description', ''),
                    "source_name": source_name,
                    "source_url": entry.link,
                    "published_at": pub_date or now
                })
                
            return articles
        except Exception as e:
            print(f"RSS fetch error: {e}")
            return []
