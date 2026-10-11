import json
import time
import os
import csv
from datetime import datetime

# Import application modules
from app.config import settings
from app.services.nlp.extraction import EventExtractor
from app.services.news.rss import GoogleNewsRSSProvider
from app.services.news.social import RedditTrafficProvider
from app.services.geo.road_matcher import RoadMatcher
from app.schemas.event import GeoLocation

# Create directories
DIRS = ['llm_benchmark', 'source_benchmark', 'fusion', 'ablation', 'geospatial', 'end_to_end']
for d in DIRS:
    os.makedirs(f'results/{d}', exist_ok=True)

# 1. Load Evaluation Subset
with open('backend/eval_subset_raw.json', 'r', encoding='utf-8') as f:
    eval_articles = json.load(f)

# Mock ground truth for the subset
GT = {
    'f11d3441-4bfc-4588-94b9-f2b73a1e1ecb': {'event_type': 'TRAFFIC_DIVERSION', 'city': 'Pune'},
    '7554e602-c81c-4810-aa06-79b62ef90d20': {'event_type': 'TRAFFIC_DIVERSION', 'city': 'Delhi'},
    'cf986db8-df1a-4a63-8f9b-6451fc7b7a82': {'event_type': 'TRAFFIC_DIVERSION', 'city': 'Delhi'},
    'b2370f16-1bf4-453b-a8d5-d62692049c6a': {'event_type': 'TRAFFIC_DIVERSION', 'city': 'Hyderabad'},
    'bff74af6-4aba-47fa-b50a-10618ba71639': {'event_type': 'TRAFFIC_DIVERSION', 'city': 'Delhi'}
}

# Ensure reproducible environment info
env_info = {
    "os": "Windows-11",
    "cpu": "AMD64 16-core",
    "ram_gb": 16.5,
    "gpu": "NVIDIA RTX 3060 Laptop 6GB",
    "framework": "FastAPI + Llama3/Ollama",
    "dataset_size": len(eval_articles),
    "timestamp": datetime.utcnow().isoformat()
}
with open('results/environment_info.json', 'w') as f:
    json.dump(env_info, f, indent=2)

def run_llm_benchmark():
    print("Running LLM Benchmark (Stage A)...")
    models = ['llama3:8b', 'qwen2.5:14b', 'qwen2.5-coder:14b', 'llava:13b']
    results = []
    
    for model in models:
        print(f"  Testing {model}...")
        settings.OLLAMA_MODEL = model # Override config
        extractor = EventExtractor()
        
        valid_json = 0
        total_latency = 0
        correct_event_type = 0
        gt_count = 0
        
        for art in eval_articles[:5]: # Use 5 for speed in benchmark
            start_t = time.time()
            try:
                ext = extractor.extract(art['title'], art['text'], art['id'])
                latency = time.time() - start_t
                total_latency += latency
                
                if ext:
                    valid_json += 1
                    # Check GT
                    if art['id'] in GT:
                        gt_count += 1
                        if ext.event_type == GT[art['id']]['event_type']:
                            correct_event_type += 1
            except Exception as e:
                print(f"Error extracting with {model}: {e}")
        
        metrics = {
            "experiment_id": f"llm_{model.replace(':', '_')}",
            "experiment_type": "llm_benchmark",
            "model": model,
            "provider": "ollama",
            "sample_count": 5,
            "valid_json_rate": valid_json / 5.0,
            "latency_avg": total_latency / 5.0 if valid_json else 0,
            "event_f1": (correct_event_type / gt_count) if gt_count > 0 else 0, # Simplified accuracy as F1 proxy for this run
            "timestamp": datetime.utcnow().isoformat()
        }
        results.append(metrics)
    
    # Save JSON
    with open('results/llm_benchmark/llm_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    # Save CSV
    with open('results/llm_benchmark/llm_results.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    
    return results

def run_source_benchmark():
    print("Running News Source Benchmark (Stage B)...")
    results = []
    
    # Source 1: Google News RSS
    print("  Testing Google News RSS...")
    start_t = time.time()
    rss = GoogleNewsRSSProvider()
    try:
        rss_articles = rss.fetch_news(query="traffic diversion Delhi")
    except Exception:
        rss_articles = []
    rss_latency = time.time() - start_t
    
    results.append({
        "experiment_id": "src_rss",
        "source": "Google News RSS",
        "articles_retrieved": len(rss_articles),
        "latency_sec": rss_latency,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    # Source 2: Reddit Traffic Provider
    print("  Testing Reddit API...")
    start_t = time.time()
    reddit = RedditTrafficProvider()
    try:
        reddit_articles = reddit.fetch_social_updates()
    except Exception:
        reddit_articles = []
    reddit_latency = time.time() - start_t
    
    results.append({
        "experiment_id": "src_reddit",
        "source": "Reddit API",
        "articles_retrieved": len(reddit_articles),
        "latency_sec": reddit_latency,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    with open('results/source_benchmark/source_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    return results

def run_geospatial_benchmark():
    print("Running Geospatial Benchmark (Stage 10)...")
    matcher = RoadMatcher()
    
    # Mock some locations to match
    locs = [
        GeoLocation(original_text="Mathura Road", latitude=28.6, longitude=77.2, status="RESOLVED", location_type="ROAD"),
        GeoLocation(original_text="Nowhere", latitude=0.0, longitude=0.0, status="RESOLVED", location_type="ROAD")
    ]
    
    start_t = time.time()
    roads = matcher.match_roads(locs, radius=500)
    latency = time.time() - start_t
    
    results = [{
        "experiment_id": "geo_match_1",
        "method": "OSMnx Nearest Edge",
        "input_locations": len(locs),
        "matched_roads": len(roads),
        "latency_sec": latency,
        "timestamp": datetime.utcnow().isoformat()
    }]
    
    with open('results/geospatial/geospatial_results.json', 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    llm_res = run_llm_benchmark()
    src_res = run_source_benchmark()
    run_geospatial_benchmark()
    print("Benchmarks completed. Results saved in /results/")
