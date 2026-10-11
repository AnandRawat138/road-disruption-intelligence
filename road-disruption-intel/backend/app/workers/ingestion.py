from app.services.news.rss import GoogleNewsRSSProvider
from app.services.news.social import RedditTrafficProvider
from app.db.database import SessionLocal
from app.models.article import Article
import hashlib

def run_ingestion():
    print("Starting news and social media ingestion...")
    rss_provider = GoogleNewsRSSProvider()
    social_provider = RedditTrafficProvider()
    
    # Step 22: Query Groups and City-Specific Queries
    cities = ["Delhi", "Mumbai", "Bengaluru", "Chennai", "Kolkata", "Hyderabad", "Pune"]
    topics = {
        "TRAFFIC": ["traffic diversion", "heavy traffic jam", "route diverted", "bottleneck"],
        "DISASTER": ["highway landslide", "road cave-in", "waterlogging road closed", "flood road blocked"],
        "ACCIDENT": ["accident closed highway", "multi-vehicle crash road block"],
        "INFRASTRUCTURE": ["bridge closed", "flyover repair", "highway construction diversion"],
        "EVENTS": ["traffic curfew", "vip movement blocked road", "protest blocking highway", "traffic advisory"]
    }
    
    all_articles = []
    
    # 1. Fetch from Expanded RSS Queries
    for city in cities:
        for group, keywords in topics.items():
            for kw in keywords:
                # E.g. "traffic diversion Delhi"
                q = f"{kw} {city}"
                all_articles.extend(rss_provider.fetch_news(query=q))
        
    # 2. Fetch from Free Social Media (Reddit blocked unauthenticated API recently)
    # social_posts = social_provider.fetch_social_updates()
    # all_articles.extend(social_posts)
    
    db = SessionLocal()
    try:
        new_count = 0
        seen_urls = set()
        for data in all_articles:
            url = data['source_url']
            
            if url in seen_urls:
                continue
            seen_urls.add(url)
            
            exists = db.query(Article).filter(Article.source_url == url).first()
            if not exists:
                content_hash = hashlib.md5(f"{data['title']}-{url}".encode()).hexdigest()
                article = Article(
                    title=data['title'],
                    description=data.get('description', ''),
                    content=data.get('content', ''),
                    source_name=data.get('source_name', 'Unknown'),
                    source_url=url,
                    published_at=data.get('published_at'),
                    content_hash=content_hash,
                    status="PENDING"
                )
                db.add(article)
                new_count += 1
        
        db.commit()
        print(f"Ingested {new_count} new articles.")
    except Exception as e:
        db.rollback()
        print(f"Error ingesting news: {e}")
    finally:
        db.close()
