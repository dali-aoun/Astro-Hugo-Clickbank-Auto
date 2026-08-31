"""
Fetches Google Trends related queries for a product/category.
Results are cached 24h in trends_cache.json to avoid rate limits.
Always fails silently — returns [] if any error.
"""

import json
import os
import time
from datetime import datetime, timedelta

_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE_FILE = os.path.join(_DIR, "trends_cache.json")
_CACHE_TTL_H = 24


def _load_cache():
    try:
        with open(_CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache):
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception:
        pass


def get_trending_terms(product_name, category_slug, max_terms=5):
    """
    Returns up to max_terms trending search terms related to product_name.
    Pulls 7-day rising & top queries from Google Trends (US, EN).
    Falls back to [] on any error.
    """
    cache = _load_cache()
    key = f"{product_name}_{category_slug}".lower().replace(" ", "_")

    if key in cache:
        entry = cache[key]
        try:
            cached_at = datetime.fromisoformat(entry["cached_at"])
            if datetime.now() - cached_at < timedelta(hours=_CACHE_TTL_H):
                return entry["terms"]
        except Exception:
            pass

    terms = []
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(
            hl="en-US", tz=360,
            timeout=(10, 25), retries=2, backoff_factor=0.5
        )
        keyword = f"{product_name} supplement"
        pytrends.build_payload([keyword], timeframe="now 7-d", geo="US")
        time.sleep(1)
        related = pytrends.related_queries()

        if keyword in related and related[keyword]:
            rising = related[keyword].get("rising")
            if rising is not None and not rising.empty:
                terms.extend(rising["query"].head(3).tolist())
            top = related[keyword].get("top")
            if top is not None and not top.empty and len(terms) < max_terms:
                terms.extend(top["query"].head(max_terms - len(terms)).tolist())

        stopwords = {"supplement", "supplements", "review", "reviews", "buy", "price", "where"}
        terms = [t for t in terms if t and len(t) > 3 and t.lower() not in stopwords][:max_terms]

    except Exception as e:
        print(f"  [trends] {product_name}: {e}")
        terms = []

    cache[key] = {"cached_at": datetime.now().isoformat(), "terms": terms}
    _save_cache(cache)
    return terms


def terms_to_hashtags(terms):
    """Convert a list of terms to Pinterest/Instagram hashtag string."""
    return " ".join(
        "#" + t.title().replace(" ", "").replace("-", "")
        for t in terms
    )
