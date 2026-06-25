import datetime
from zoneinfo import ZoneInfo
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .scraper import RSS

# Initialize the FastAPI application
app = FastAPI(
    title="RSS - Reddit Scraper",
    description="REST API for Reddit Scraper (RSS). Provides endpoints for searching, scraping post details, and harvesting user/subreddit data.",
    version="0.1.0",
)

# Initialize the shared scraper instance (singleton-like pattern for the API)
scraper = RSS()


# --- Pydantic Models for API Responses ---

class PostBase(BaseModel):
    """Summarized post data for search results."""
    title: str
    link: str
    description: str
    created_utc: Optional[float]


class PostDetailed(BaseModel):
    """Comprehensive data for a single post, including the full comment tree."""
    title: str
    body: str
    comments: List[dict]
    image_url: Optional[str]
    thumbnail_url: Optional[str]
    url: str
    permalink: str


class UserItem(BaseModel):
    """Represents a single activity item (Post or Comment) from a user's feed."""
    type: str
    title: Optional[str] = None
    subreddit: str
    url: str
    created_utc: float
    body: Optional[str] = None


class SubredditPost(BaseModel):
    """Detailed metadata for a post within a subreddit listing."""
    title: str
    author: str
    permalink: str
    score: int
    num_comments: int
    created_utc: float
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None


# --- Helper Functions ---

def apply_time_slot_filter(results: List[dict], time_slot: str) -> List[dict]:
    """
    Filters a list of results based on a daily time range in IST.

    Args:
        results (List[dict]): List of post/comment dictionaries.
        time_slot (str): Time range string (e.g., '10:00-14:00').

    Returns:
        List[dict]: Subset of the results falling within the specified time.
    """
    try:
        # Parse HH:MM-HH:MM format
        start_str, end_str = time_slot.split("-")
        slot_start = datetime.datetime.strptime(start_str.strip(), "%H:%M").time()
        slot_end = datetime.datetime.strptime(end_str.strip(), "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid time-slot format. Use HH:MM-HH:MM")

    filtered = []
    # Try to load IST timezone, fallback to manual offset if tzdata is missing
    try:
        ist_tz = ZoneInfo("Asia/Kolkata")
    except Exception:
        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    
    for item in results:
        created_utc = item.get("created_utc")
        if not created_utc:
            continue
            
        # 1. Convert Reddit's UTC timestamp to a localized IST datetime object
        # 2. Extract the time component for comparison
        post_time = datetime.datetime.fromtimestamp(created_utc, tz=datetime.timezone.utc).astimezone(ist_tz).time()
        
        # Handle standard slots (10:00-12:00) vs wrapped slots (22:00-02:00)
        if slot_start <= slot_end:
            if slot_start <= post_time <= slot_end:
                filtered.append(item)
        else:  # Range crosses midnight
            if post_time >= slot_start or post_time <= slot_end:
                filtered.append(item)
    return filtered


# --- API Routes ---

@app.get("/")
async def root():
    """Root endpoint providing documentation links and health status."""
    return {
        "message": "Welcome to RSS API (Reddit Scraper)",
        "docs": "/docs",
        "status": "active"
    }


@app.get("/search", response_model=List[PostBase])
async def search(
    q: str = Query(..., description="The search query"),
    limit: int = Query(10, ge=1, le=100),
    sort: str = "relevance",
    time: str = "all",
    time_slot: Optional[str] = Query(None, description="Filter by time of day in IST (HH:MM-HH:MM)")
):
    """
    Searches Reddit for posts matching the query.
    Note: Time-slot filtering is performed locally on the fetched batch.
    """
    # Over-fetch if we are filtering locally to ensure we returned the requested count
    fetch_limit = limit * 10 if time_slot else limit
    results = scraper.search_reddit(query=q, limit=fetch_limit, sort=sort, time_filter=time)
    
    if time_slot:
        results = apply_time_slot_filter(results, time_slot)
        return results[:limit]
        
    if not results:
        return []
    return results


@app.get("/post", response_model=PostDetailed)
async def get_post_details(permalink: str = Query(..., description="The permalink of the post (e.g., /r/python/comments/...)")):
    """Fetches full content, media URLs, and the nested comment tree for a post."""
    # Ensure permalink starts with a slash for internal scraper consistency
    if not permalink.startswith("/"):
        permalink = f"/{permalink}"
        
    details = scraper.scrape_post_details(permalink)
    if not details:
        raise HTTPException(status_code=404, detail="Post not found or failed to scrape")
    return details


@app.get("/comments", response_model=List[dict])
async def get_post_comments(permalink: str = Query(..., description="The permalink of the post")):
    """Fetches ONLY the recursive comment tree for a specific post."""
    if not permalink.startswith("/"):
        permalink = f"/{permalink}"
        
    details = scraper.scrape_post_details(permalink)
    if not details:
        raise HTTPException(status_code=404, detail="Post not found or failed to scrape")
    return details.get("comments", [])


@app.get("/user/{username}", response_model=List[UserItem])
async def get_user_activity(
    username: str,
    limit: int = Query(10, ge=1, le=100)
):
    """Aggregates a user's recent posts and comments into a chronological feed."""
    results = scraper.scrape_user_data(username=username, limit=limit)
    if not results:
        return []
    return results


@app.get("/subreddit/{subreddit}", response_model=List[SubredditPost])
async def get_subreddit_posts(
    subreddit: str,
    limit: int = Query(10, ge=1, le=100),
    category: str = "hot",
    time: str = "all",
    time_slot: Optional[str] = Query(None, description="Filter by time of day in IST (HH:MM-HH:MM)")
):
    """Fetches a feed (hot, top, new) from a specific subreddit or user."""
    try:
        # Over-fetch for local filtering if time_slot is provided
        fetch_limit = limit * 10 if time_slot else limit
        results = scraper.fetch_subreddit_posts(
            subreddit=subreddit,
            limit=fetch_limit,
            category=category,
            time_filter=time
        )
        
        if time_slot:
            results = apply_time_slot_filter(results, time_slot)
            return results[:limit]
            
        return results
    except ValueError as e:
        # Catch validation errors from the scraper (e.g., invalid category)
        raise HTTPException(status_code=400, detail=str(e))

