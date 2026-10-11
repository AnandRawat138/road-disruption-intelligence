import urllib.request
import json
from typing import List, Dict
from datetime import datetime

class RedditTrafficProvider:
    def __init__(self):
        self.subreddits = ["delhi", "mumbai", "bangalore", "india"]
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) RoadDisruptionBot/1.0'}

    def fetch_social_updates(self) -> List[Dict]:
        """
        Fetches free, real-time social media reports from regional subreddits regarding traffic.
        """
        articles = []
        for sub in self.subreddits:
            try:
                # Search for recent traffic, highway, or gridlock posts
                url = f"https://www.reddit.com/r/{sub}/search.json?q=traffic+OR+highway+OR+gridlock&restrict_sr=on&sort=new&t=week"
                req = urllib.request.Request(url, headers=self.headers)
                
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode())
                    
                    for child in data.get('data', {}).get('children', [])[:5]:
                        post = child['data']
                        
                        # Only take text posts with actual content or descriptive titles
                        articles.append({
                            "title": post.get('title', ''),
                            "description": post.get('selftext', '')[:500],
                            "content": post.get('selftext', ''),
                            "source_name": f"Reddit (r/{sub})",
                            "source_url": f"https://www.reddit.com{post.get('permalink', '')}",
                            "published_at": datetime.fromtimestamp(post.get('created_utc', datetime.utcnow().timestamp()))
                        })
            except Exception as e:
                print(f"Reddit scrape error for r/{sub}: {e}")
                
        return articles
