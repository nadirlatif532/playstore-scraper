import subprocess
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from flask import Flask, request, jsonify
from flask_cors import CORS
from google_play_scraper import search as python_search, app as get_details
from datetime import datetime, timedelta
import threading

app = Flask(__name__)
CORS(app)

# In-memory cache for new releases
_cache = {"data": None, "timestamp": None}
_cache_lock = threading.Lock()
CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours

# Configuration
WORKERS = 40  # Controlled parallelization
MAX_RETRIES = 3
REQUEST_TIMEOUT = 10  # seconds per app
DAYS_THRESHOLD = 90  # default filter (90 days for comprehensive coverage)
CANDIDATE_LIMIT = 500  # max candidates to enrich
CHART_FETCH_COUNT = 100  # apps to fetch per category

# All 17 game categories
GAME_CATEGORIES = [
    "GAME_ACTION",
    "GAME_ADVENTURE",
    "GAME_ARCADE",
    "GAME_BOARD",
    "GAME_CARD",
    "GAME_CASINO",
    "GAME_CASUAL",
    "GAME_EDUCATIONAL",
    "GAME_MUSIC",
    "GAME_PUZZLE",
    "GAME_RACING",
    "GAME_ROLE_PLAYING",
    "GAME_SIMULATION",
    "GAME_SPORTS",
    "GAME_STRATEGY",
    "GAME_TRIVIA",
    "GAME_WORD",
]

# Evergreen search terms (no year)
SEARCH_TERMS = [
    "new game release",
    "latest game",
    "new android game",
    "just released game",
    "new mobile game",
    "new free game",
    "new 2026 game",
]


def call_node_scraper(action, params, fallback_query="games"):
    """
    Tries the high-performance Node scraper first.
    If it fails, it falls back to the stable Python scraper.
    """
    try:
        # 1. MAP COLLECTION NAMES: Node expects "TOP_FREE", not "topselling_free"
        if "collection" in params:
            mapping = {
                "topselling_free": "TOP_FREE",
                "topselling_paid": "TOP_PAID",
                "topgrossing": "GROSSING",
                "new_free": "NEW_FREE",
                "new_paid": "NEW_PAID",
            }
            params["collection"] = mapping.get(
                params["collection"], params["collection"]
            ).upper()

        # 2. Run the Node bridge
        result = subprocess.run(
            ["node", "bridge.js", action, json.dumps(params)],
            capture_output=True,
            encoding="utf-8",
            errors="replace",  # Replace undecodable characters instead of crashing
            check=True,
        )
        return json.loads(result.stdout.strip())

    except Exception as e:
        stderr_msg = getattr(e, "stderr", str(e))
        print(f"⚠️ Hybrid Error during {action}: {stderr_msg}. Falling back to Python.")

        # FALLBACK Logic
        try:
            # Note: Python library only supports search/details
            if action == "suggest":
                # Python library doesn't have suggest, we just return empty or search term
                return [fallback_query]

            # fallback to search
            return python_search(fallback_query, n_hits=30)
        except Exception as e_inner:
            print(f"❌ Critical Failure: Both scrapers failed. {e_inner}")
            return []


def filter_hidden_gems(app_list):
    """
    Identifies high-quality apps with mid-to-low install counts.
    """
    gems = []
    seen = set()
    if not isinstance(app_list, list):
        return gems

    for entry in app_list:
        app_id = entry.get("appId")
        if not app_id or app_id in seen:
            continue
        seen.add(app_id)

        score = entry.get("score") or 0
        # Handle various install formats (minInstalls as int or installs as string)
        installs = entry.get("minInstalls") or entry.get("installs") or 0

        if isinstance(installs, str):
            # Strip non-digits (like '+', ',') and convert to int
            installs = int("".join(filter(str.isdigit, installs)) or 0)

        # BLUEPRINT CRITERIA: High Rating (4.2+) + Healthy Growth (5k to 50M installs)
        # Aligned with frontend normalization logic
        if score >= 4.2 and 5000 <= installs <= 50000000:
            gems.append(entry)
    return sorted(gems, key=lambda x: x.get("score", 0), reverse=True)


def fetch_app_details_batch(apps):
    """
    Parallel fetch details for a list of apps to retrieve the 'released' date.
    This is necessary because the Play Store chart list doesn't include it.
    """
    if not apps:
        return []

    print(f"🚀 Enriching {len(apps)} apps with detail data...")

    def fetch_one_detail(app_obj):
        app_id = app_obj.get("appId")
        if not app_id:
            return app_obj
        try:
            details = call_node_scraper("app", {"appId": app_id})
            if details and isinstance(details, dict):
                # Enrich original object with detail fields
                app_obj["released"] = details.get("released")
                app_obj["description"] = details.get("description")
                app_obj["version"] = details.get("version")
                app_obj["installs"] = details.get("installs")
                app_obj["genre"] = details.get("genre")
        except Exception as e:
            print(f"⚠️ Failed to fetch details for {app_id}: {e}")
        return app_obj

    # Use a higher worker count for network-bound tasks
    with ThreadPoolExecutor(max_workers=50) as executor:
        enriched_apps = list(executor.map(fetch_one_detail, apps))

    return enriched_apps


def parse_google_play_date(date_str):
    """
    Parses Google Play's released date string into a datetime object.
    Handles formats like: "Sep 20, 2012", "23 Sept 2022", "Sep 20 2012"
    """
    if not date_str or not isinstance(date_str, str):
        return None
    from datetime import datetime
    import re

    clean_str = date_str.strip()

    # Normalize "Sept" variations to "Sep"
    clean_str = re.sub(r"Sept\.?", "Sep", clean_str, flags=re.IGNORECASE)

    # Remove punctuation and normalize spaces
    clean_str = re.sub(r"[.,]", "", clean_str)
    clean_str = re.sub(r"\s+", " ", clean_str).strip()

    # Try different format combinations
    formats = [
        "%b %d %Y",  # Sep 20 2012
        "%b %d %Y",  # Sep 20 2012
        "%d %b %Y",  # 20 Sep 2022
        "%B %d %Y",  # September 20 2012
        "%d %B %Y",  # 20 September 2022
    ]

    for fmt in formats:
        try:
            return datetime.strptime(clean_str, fmt)
        except ValueError:
            continue
    return None


def filter_new_releases(app_list, days_threshold=90):
    """
    Filters and sorts apps based on their original release date.
    Apps without a release date are marked as 'dateUnverified' but kept.
    """
    from datetime import datetime, timedelta

    if not isinstance(app_list, list):
        return []

    cutoff_date = datetime.now() - timedelta(days=days_threshold)
    results = []
    seen = set()

    for app_data in app_list:
        app_id = app_data.get("appId")
        if not app_id or app_id in seen:
            continue
        seen.add(app_id)

        released_str = app_data.get("released")
        released_date = parse_google_play_date(released_str)

        # If we have a date, check if it's within threshold
        if released_date:
            if released_date >= cutoff_date:
                app_data["released_timestamp"] = released_date.timestamp()
                app_data["dateUnverified"] = False
                results.append(app_data)
        else:
            # If NO date, we mark as unverified instead of rejecting (user request)
            app_data["released_timestamp"] = 0  # Push to bottom
            app_data["dateUnverified"] = True
            results.append(app_data)

    # Sort by release date descending (newest first, unverified at bottom)
    return sorted(
        results,
        key=lambda x: (
            not x.get("dateUnverified", False),
            x.get("released_timestamp", 0),
        ),
        reverse=True,
    )


def fetch_with_retry(action, params, max_retries=MAX_RETRIES, timeout=REQUEST_TIMEOUT):
    """
    Calls the node scraper with retry logic and timeout.
    """
    for attempt in range(max_retries):
        try:
            result = call_node_scraper(action, params)
            return result
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = (2**attempt) * 0.5  # Exponential backoff: 0.5s, 1s, 2s
                print(
                    f"⚠️ Attempt {attempt + 1} failed for {action}: {e}. Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
            else:
                print(f"❌ All {max_retries} attempts failed for {action}: {e}")
                return None
    return None


def fetch_app_details_robust(app_id, max_retries=MAX_RETRIES):
    """
    Fetches app details with retry logic and timeout.
    Returns the details dict or None if all attempts fail.
    """
    for attempt in range(max_retries):
        try:
            details = call_node_scraper("app", {"appId": app_id})
            return details
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = (2**attempt) * 0.5
                time.sleep(wait_time)
            else:
                print(
                    f"❌ Failed to fetch details for {app_id} after {max_retries} attempts"
                )
                return None
    return None


def fetch_chart_for_category(cat, num=None):
    """
    Fetches TOP_FREE apps from a single category.
    """
    if num is None:
        num = CHART_FETCH_COUNT
    try:
        return (
            call_node_scraper(
                "list",
                {
                    "category": cat,
                    "collection": "TOP_FREE",
                    "num": num,
                    "fullDetail": False,
                },
            )
            or []
        )
    except Exception as e:
        print(f"⚠️ Failed to fetch chart for {cat}: {e}")
        return []


def fetch_search_results(term, num=50):
    """
    Fetches search results for a term.
    """
    try:
        return call_node_scraper("search", {"term": term, "num": num}) or []
    except Exception as e:
        print(f"⚠️ Failed to search for '{term}': {e}")
        return []


def enrich_app_with_details(app_obj):
    """
    Enriches an app object with details (including 'released' date).
    Uses retry logic for reliability.
    """
    app_id = app_obj.get("appId")
    if not app_id:
        return app_obj

    details = fetch_app_details_robust(app_id)
    if details and isinstance(details, dict):
        app_obj["released"] = details.get("released")
        app_obj["description"] = details.get("description")
        app_obj["version"] = details.get("version")
        app_obj["installs"] = details.get("installs")
        app_obj["genre"] = details.get("genre")
        app_obj["score"] = details.get("score", app_obj.get("score"))
        app_obj["free"] = details.get("free", True)

    return app_obj


def discover_new_releases(days_threshold=DAYS_THRESHOLD, limit=100):
    """
    Multi-source discovery for new releases.
    1. Charts from all 17 game categories
    2. Search terms
    3. Deduplicate and track sources
    4. Enrich with detail data
    5. Filter by release date
    6. Rank by multi-source scoring
    """
    print(f"🚀 Starting new releases discovery (threshold: {days_threshold} days)...")

    # Stage 1: Discover from charts (all 17 categories)
    print(
        f"📊 Fetching TOP_FREE from all 17 game categories ({CHART_FETCH_COUNT} per category)..."
    )
    chart_apps = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch_chart_for_category, GAME_CATEGORIES))
        for batch in results:
            if isinstance(batch, list):
                for app in batch:
                    if app:
                        app["_source_charts"] = True
                        chart_apps.append(app)
    print(f"   Found {len(chart_apps)} apps from charts")

    # Stage 1b: Discover from search terms
    print(f"🔍 Fetching search results ({len(SEARCH_TERMS)} terms, 50 results each)...")
    search_apps = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(
            executor.map(lambda t: fetch_search_results(t, 50), SEARCH_TERMS)
        )
        for batch in results:
            if isinstance(batch, list):
                for app in batch:
                    if app:
                        app["_source_search"] = True
                        search_apps.append(app)
    print(f"   Found {len(search_apps)} apps from search")

    # Stage 2: Deduplicate and combine
    seen_ids = {}
    all_candidates = []

    for app in chart_apps:
        app_id = app.get("appId")
        if app_id and app_id not in seen_ids:
            seen_ids[app_id] = True
            all_candidates.append(app)

    for app in search_apps:
        app_id = app.get("appId")
        if app_id and app_id not in seen_ids:
            seen_ids[app_id] = True
            all_candidates.append(app)
        elif app_id in seen_ids:
            # Mark app as appearing in both sources
            for candidate in all_candidates:
                if candidate.get("appId") == app_id:
                    candidate["_source_search"] = True
                    break

    print(f"   Total unique candidates: {len(all_candidates)}")

    # Stage 3: Enrich with details (controlled parallelization)
    candidates_to_enrich = all_candidates[:CANDIDATE_LIMIT]
    print(
        f"🔍 Enriching {len(candidates_to_enrich)} candidates with detail data (25 workers)..."
    )

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        enriched = list(executor.map(enrich_app_with_details, candidates_to_enrich))

    # Stage 4: Filter by release date
    print(f"📅 Filtering by release date (within {days_threshold} days)...")
    cutoff_date = datetime.now() - timedelta(days=days_threshold)
    filtered_results = []

    for app in enriched:
        released_str = app.get("released")
        released_date = parse_google_play_date(released_str)

        if released_date:
            if released_date >= cutoff_date:
                app["released_timestamp"] = released_date.timestamp()
                app["days_old"] = (datetime.now() - released_date).days
                filtered_results.append(app)
        # Skip apps without release date (can't verify they're new)

    print(
        f"   Found {len(filtered_results)} apps released within {days_threshold} days"
    )

    # Stage 5: Multi-source scoring and ranking
    def calculate_score(app):
        score = 0
        # Source bonus: +2 for charts, +2 for search, +3 for both
        if app.get("_source_charts") and app.get("_source_search"):
            score += 3
        elif app.get("_source_charts"):
            score += 2
        elif app.get("_source_search"):
            score += 2
        # Recency bonus: newer = higher score
        days_old = app.get("days_old", 999)
        if days_old <= 3:
            score += 5
        elif days_old <= 7:
            score += 3
        elif days_old <= 14:
            score += 1
        # Rating bonus
        rating = app.get("score", 0) or 0
        score += rating
        return score

    for app in filtered_results:
        app["discovery_score"] = calculate_score(app)
        # Clean up internal tracking fields
        app.pop("_source_charts", None)
        app.pop("_source_search", None)

    # Sort by discovery score (descending)
    filtered_results.sort(key=lambda x: x.get("discovery_score", 0), reverse=True)

    # Apply limit
    final_results = filtered_results[:limit]

    print(f"✅ Returning top {len(final_results)} new releases")

    return {
        "totalFound": len(final_results),
        "daysThreshold": days_threshold,
        "lastUpdated": datetime.now().isoformat(),
        "apps": final_results,
    }


def get_cached_new_releases(
    days_threshold=DAYS_THRESHOLD, limit=100, force_refresh=False
):
    """
    Returns cached new releases if valid, otherwise fetches fresh data.
    """
    global _cache

    with _cache_lock:
        now = time.time()
        cache_valid = (
            _cache["data"] is not None
            and _cache["timestamp"] is not None
            and (now - _cache["timestamp"]) < CACHE_TTL_SECONDS
        )

        if cache_valid and not force_refresh:
            print("📦 Returning cached data")
            return _cache["data"]

    # Fetch fresh data
    print("🌐 Cache miss or refresh requested - fetching fresh data...")
    fresh_data = discover_new_releases(days_threshold=days_threshold, limit=limit)

    with _cache_lock:
        _cache["data"] = fresh_data
        _cache["timestamp"] = time.time()

    return fresh_data


@app.route("/")
def health_check():
    return "Hybrid Scraper is Online", 200


@app.route("/charts")
def get_charts():
    # Category must be uppercase for Node (e.g., GAME_ACTION)
    req_category = request.args.get("category", "GAME").upper()
    collection = request.args.get("collection", "topselling_free")

    # NEW RELEASES Logic: Use the improved new-releases discovery
    if collection in ["new_free", "new_paid"]:
        # Use the new multi-source discovery with caching
        result = get_cached_new_releases(
            days_threshold=90, limit=100, force_refresh=False
        )
        return jsonify(result.get("apps", []))

    # DEFAULT top charts (Not New Releases)
    return jsonify(
        call_node_scraper(
            "list",
            {
                "category": req_category,
                "collection": collection,
                "num": 40,
                "fullDetail": False,
            },
            fallback_query=req_category.replace("GAME_", "").lower(),
        )
    )


@app.route("/new-releases")
def new_releases():
    """
    Dedicated endpoint for discovering new game releases.
    Uses multi-source discovery with controlled parallelization,
    retry logic, and caching.
    """
    days = int(request.args.get("days", DAYS_THRESHOLD))
    limit = int(request.args.get("limit", 100))
    force_refresh = request.args.get("refresh", "").lower() in ("true", "1", "yes")

    print(
        f"📱 New releases request: days={days}, limit={limit}, force_refresh={force_refresh}"
    )

    result = get_cached_new_releases(
        days_threshold=days, limit=limit, force_refresh=force_refresh
    )

    return jsonify(result)


@app.route("/similar/<app_id>")
def get_similar(app_id):
    return jsonify(
        call_node_scraper(
            "similar", {"appId": app_id}, fallback_query=app_id.split(".")[-1]
        )
    )


@app.route("/discover-hits")
def discover_hits():
    category = request.args.get("category", "GAME").upper()

    print(f"🚀 Starting hidden gem discovery for {category}...")

    # 1. Get seed games for this category (Top Chart)
    seed_apps = call_node_scraper(
        "list",
        {"category": category, "collection": "TOP_FREE", "num": 15},
        fallback_query=category.replace("GAME_", "").lower(),
    )

    discovery_pool = []
    if isinstance(seed_apps, list) and seed_apps:
        # Fan-out to top performers to find similar apps
        seed_candidates = seed_apps[:5]

        def fetch_similar(seed):
            app_id = seed.get("appId")
            if app_id:
                return call_node_scraper(
                    "similar", {"appId": app_id}, seed.get("title", "game")
                )
            return []

        # Step 2 — Parallelize /similar fetches to avoid timeouts
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(fetch_similar, seed_candidates))
            for res in results:
                if isinstance(res, list):
                    discovery_pool.extend(res)

    # 3. Filter and Deduplicate for hidden gems
    hits = filter_hidden_gems(discovery_pool)

    print(
        f"✅ Discovery complete: Scanned {len(discovery_pool)} apps, found {len(hits)} gems."
    )

    return jsonify(
        {
            "category": category,
            "total_scanned": len(discovery_pool),
            "hidden_gems": hits,
        }
    )


@app.route("/details/<app_id>")
def details(app_id):
    try:
        return jsonify(get_details(app_id))
    except Exception:
        return jsonify({"error": "App not found"}), 404


@app.route("/suggest")
def suggest():
    term = request.args.get("term", "")
    return jsonify(call_node_scraper("suggest", {"term": term}, term))


@app.route("/search")
def search():
    term = request.args.get("term", "")
    num = request.args.get("num", "20")
    lang = request.args.get("lang", "en")
    country = request.args.get("country", "us")

    if not term:
        return jsonify({"error": "Search term is required"}), 400

    return jsonify(
        call_node_scraper(
            "search",
            {"term": term, "num": int(num), "lang": lang, "country": country},
            term,
        )
    )


if __name__ == "__main__":
    # Standard Hugging Face port
    app.run(host="0.0.0.0", port=7860, debug=True)
