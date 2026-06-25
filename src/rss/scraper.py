from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .sessions import RandomUserAgentSession


class RSS:
    """
    Reddit Scraper (RSS).
    
    A client for scraping data from Reddit's public JSON API. 
    It supports:
    - Retries and backoff for rate-limiting.
    - Proxies for IP rotation.
    - Random User-Agents to prevent fingerprinting.
    - Recursive comment extraction.
    """

    # Using __slots__ to optimize memory usage for large numbers of scraper instances
    __slots__ = ("headers", "session", "proxy", "timeout")

    def __init__(
        self,
        proxy: Optional[str] = None,
        timeout: int = 10,
        random_user_agent: bool = True,
    ):
        """
        Initializes the RSS client with HTTP settings.

        Args:
            proxy (Optional[str]): Proxy URL (e.g., http://proxy:port).
            timeout (int): Seconds to wait for a response.
            random_user_agent (bool): If True, uses the RandomUserAgentSession.
        """
        # Select session type (Standard or Random User-Agent)
        self.session = RandomUserAgentSession() if random_user_agent else requests.Session()
        self.proxy = proxy
        self.timeout = timeout

        # Configure retry strategy for resilient network operations
        retries = Retry(
            total=5,
            backoff_factor=2,  # Wait 2, 4, 8, 16, 32 seconds between retries
            status_forcelist=[429, 500, 502, 503, 504], # Retry on rate limit or server errors
        )

        # Apply the retry strategy to all HTTPS requests
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

        if proxy:
            self.session.proxies.update({"http": proxy, "https": proxy})

    def handle_search(
        self, url: str, params: Dict[str, Any], after: Optional[str] = None, before: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Executes a search request and parses the standard 'listing' response.

        Args:
            url (str): Target Reddit JSON URL.
            params (Dict[str, Any]): API parameters (q, limit, sort, etc.).
            after (Optional[str]): Pagination token for the next page.
            before (Optional[str]): Pagination token for the previous page.

        Returns:
            Tuple[List[Dict[str, Any]], Optional[str]]: Parsed post list and the 'after' token.
        """
        if after:
            params["after"] = after
        if before:
            params["before"] = before

        try:
            # Perform the GET request to Reddit's JSON endpoint
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            logging.info("Search request successful")
        except requests.RequestException as e:
            logging.error("Search request unsuccessful for %s: %s", url, e)
            return [], None

        try:
            data = response.json()
            inner_data = data.get("data", {})
            results = []
            
            # Map Reddit's internal 'children' objects to a simplified dictionary format
            for post in inner_data.get("children", []):
                post_data = post["data"]
                results.append(
                    {
                        "title": post_data["title"],
                        "link": f"https://www.reddit.com{post_data['permalink']}",
                        "description": post_data.get("selftext", "")[:269], # Truncate description
                        "created_utc": post_data.get("created_utc"),
                    }
                )
            
            # Extract the pagination token for subsequent calls
            after_token = inner_data.get("after")
            logging.info("Search Results Returned %d Results", len(results))
            return results, after_token
        except (ValueError, KeyError) as e:
            logging.error("Failed to parse search results: %s", e)
            return [], None

    def search_reddit(
        self,
        query: str,
        limit: int = 10,
        sort: str = "relevance",
        time_filter: str = "all",
    ) -> List[Dict[str, Any]]:
        """
        Searches all of Reddit with support for automatic pagination.

        Args:
            query (str): Keyword(s) to search for.
            limit (int): Max results. Use 0 for unlimited (hard cap 1000 for safety).
            sort (str): Sorting method (relevance, hot, top, new, comments).
            time_filter (str): Time range (hour, day, week, month, year, all).

        Returns:
            List[Dict[str, Any]]: Flattened list of post dictionaries.
        """
        url = "https://www.reddit.com/search.json"
        all_results = []
        after = None
        
        # Reddit API generally caps at 1000 items per listing
        max_results = limit if limit > 0 else 1000
        is_unlimited = limit <= 0
        
        while len(all_results) < max_results:
            # Reddit limits batch size to 100 per request
            batch_limit = min(100, max_results - len(all_results)) if not is_unlimited else 100
            
            params = {
                "q": query,
                "limit": batch_limit,
                "sort": sort,
                "type": "link", # We only want posts, not subreddits or users
                "t": time_filter,
                "raw_json": 1 # Request unescaped JSON data
            }
            
            results, after = self.handle_search(url, params, after=after)
            if not results:
                break # Exit if no more results are found
                
            all_results.extend(results)
            
            if not after:
                break # Exit if we reached the last page
                
            if len(all_results) >= max_results and not is_unlimited:
                break # Exit if we reached the user's limit

            # Politeness delay to avoid IP blocking
            time.sleep(random.uniform(1, 2))
            
        return all_results[:limit] if not is_unlimited else all_results

    def search_subreddit(
        self,
        subreddit: str,
        query: str,
        limit: int = 10,
        after: Optional[str] = None,
        before: Optional[str] = None,
        sort: str = "relevance",
    ) -> List[Dict[str, Any]]:
        """
        Performs a search constrained to a specific subreddit.

        Args:
            subreddit (str): Subreddit name without 'r/'.
            query (str): Keyword(s).
            limit (int): Max results.
            after/before (str): Pagination tokens.
            sort (str): Sort order.
        """
        url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {
            "q": query, 
            "limit": limit, 
            "sort": sort, 
            "type": "link", 
            "restrict_sr": "on" # Constraint search to the current subreddit
        }
        return self.handle_search(url, params, after, before)

    def scrape_post_details(self, permalink: str) -> Optional[Dict[str, Any]]:
        """
        Fetches full details for a post by its permalink, including the comment tree.

        Args:
            permalink (str): The Reddit permalink (e.g., /r/topic/comments/id/title).

        Returns:
            Optional[Dict[str, Any]]: Comprehensive post data or None on failure.
        """
        # Append .json to the permalink to get the API representation
        url = f"https://www.reddit.com{permalink}.json"

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            logging.info("Post details request successful : %s", url)
        except requests.RequestException as e:
            logging.error("Post details request unsuccessful for %s: %s", url, e)
            return None

        try:
            # Reddit post data arrives as a list: [PostInfo, CommentTree]
            post_data = response.json()
            if not isinstance(post_data, list) or len(post_data) < 2:
                logging.error("Unexpected post data structure for %s", url)
                return None

            # Extract main post metadata from the first list element
            main_post = post_data[0]["data"]["children"][0]["data"]
            title = main_post["title"]
            body = main_post.get("selftext", "")

            # Specialized Media extraction logic
            image_url = None
            thumbnail_url = None

            # 1. Direct Image check
            if main_post.get("post_hint") == "image" and "url" in main_post:
                image_url = main_post["url"]
            # 2. Preview Image check (handles gallery items or external links with previews)
            elif "preview" in main_post and "images" in main_post["preview"]:
                image_url = main_post["preview"]["images"][0]["source"]["url"]

            # 3. Fallback to Thumbnail if no full image is found
            if "thumbnail" in main_post and main_post["thumbnail"] not in ["self", "default", "nsfw"]:
                thumbnail_url = main_post["thumbnail"]

            # Extract and flatten the comment tree from the second list element
            comments = self._extract_comments(post_data[1]["data"]["children"])
            logging.info("Successfully scraped post: %s", title)

            return {
                "title": title,
                "score": main_post.get("score", 0),  # Extract Number of Likes (Score)
                "created_utc": main_post.get("created_utc"), # Original Reddit timestamp
                "body": body,
                "comments": comments,
                "image_url": image_url,
                "thumbnail_url": thumbnail_url,
                "url": main_post.get("url", ""),
                "permalink": main_post.get("permalink", ""),
            }
        except (ValueError, KeyError, IndexError) as e:
            logging.error("Failed to parse post details for %s: %s", url, e)
            return None

    def _extract_comments(self, comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Internal recursive helper to walk down Reddit's nested comment objects.

        Args:
            comments (List[Dict[str, Any]]): List of 'children' from the comments listing.

        Returns:
            List[Dict[str, Any]]: Flattened list of comments with metadata and sub-replies.
        """
        extracted_comments = []
        for comment in comments:
            # 't1' indicates a standard comment object in Reddit's naming convention
            if isinstance(comment, dict) and comment.get("kind") == "t1":
                comment_data = comment.get("data", {})
                extracted_comment = {
                    "author": comment_data.get("author", ""),
                    "body": comment_data.get("body", ""),
                    "score": comment_data.get("score", ""),
                    "replies": [],
                }

                # If replies exist, recursively call this function to process the next level
                replies = comment_data.get("replies", "")
                if isinstance(replies, dict): # replies is an empty string if there are no replies
                    extracted_comment["replies"] = self._extract_comments(
                        replies.get("data", {}).get("children", [])
                    )
                extracted_comments.append(extracted_comment)
        return extracted_comments

    def scrape_user_data(self, username: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Collects posts and comments from a user's chronological activity feed.

        Args:
            username (str): Target Reddit username.
            limit (int): Max items to harvest.

        Returns:
            List[Dict[str, Any]]: Mixed list of posts ('t3') and comments ('t1').
        """
        logging.info("Scraping user data for %s, limit: %d", username, limit)
        base_url = f"https://www.reddit.com/user/{username}/.json"
        params = {"limit": min(limit, 100), "after": None}
        all_items = []
        count = 0

        while count < limit:
            try:
                response = self.session.get(base_url, params=params, timeout=self.timeout)
                response.raise_for_status()
                logging.info("User data request successful for %s", username)
            except requests.RequestException as e:
                logging.error("User data request unsuccessful for %s: %s", username, e)
                break

            try:
                data = response.json()
            except ValueError as e:
                logging.error("Failed to parse JSON response for user %s: %s", username, e)
                break

            if "data" not in data or "children" not in data["data"]:
                logging.error("Malformed response context for user %s", username)
                break

            items = data["data"]["children"]
            if not items:
                logging.info("No more items found for user %s.", username)
                break

            for item in items:
                kind = item["kind"]
                item_data = item["data"]
                
                # 't3' identifies a Post / Submission
                if kind == "t3":
                    post_url = f"https://www.reddit.com{item_data.get('permalink', '')}"
                    all_items.append(
                        {
                            "type": "post",
                            "title": item_data.get("title", ""),
                            "subreddit": item_data.get("subreddit", ""),
                            "url": post_url,
                            "created_utc": item_data.get("created_utc", ""),
                        }
                    )
                # 't1' identifies a Comment
                elif kind == "t1":
                    comment_url = f"https://www.reddit.com{item_data.get('permalink', '')}"
                    all_items.append(
                        {
                            "type": "comment",
                            "subreddit": item_data.get("subreddit", ""),
                            "body": item_data.get("body", ""),
                            "created_utc": item_data.get("created_utc", ""),
                            "url": comment_url,
                        }
                    )
                count += 1
                if count >= limit:
                    break

            # Handle pagination
            params["after"] = data["data"].get("after")
            if not params["after"]:
                break

            time.sleep(random.uniform(1, 2))

        logging.info("Successfully scraped user data for %s", username)
        return all_items

    def fetch_subreddit_posts(
        self, subreddit: str, limit: int = 10, category: str = "hot", time_filter: str = "all"
    ) -> List[Dict[str, Any]]:
        """
        Fetches the primary feed of a subreddit or the submissions of a user.

        Args:
            subreddit (str): Subreddit or User name.
            limit (int): Number of items.
            category (str): hot, top, new (or userhot, usertop, usernew).
            time_filter (str): Range for 'top' category.

        Returns:
            List[Dict[str, Any]]: List of post records with extracted media links.
        """
        logging.info(
            "Fetching posts for %s, limit: %d, category: %s, time_filter: %s",
            subreddit,
            limit,
            category,
            time_filter,
        )

        valid_categories = ["hot", "top", "new", "userhot", "usertop", "usernew"]
        if category not in valid_categories:
            raise ValueError(f"Category must be one of {valid_categories}")

        batch_size = min(100, limit)
        total_fetched = 0
        after = None
        all_posts = []

        while total_fetched < limit:
            # Map simplified category names to specialized Reddit URLs
            if category == "hot":
                url = f"https://www.reddit.com/r/{subreddit}/hot.json"
            elif category == "top":
                url = f"https://www.reddit.com/r/{subreddit}/top.json"
            elif category == "new":
                url = f"https://www.reddit.com/r/{subreddit}/new.json"
            elif category == "userhot":
                url = f"https://www.reddit.com/user/{subreddit}/submitted/hot.json"
            elif category == "usertop":
                url = f"https://www.reddit.com/user/{subreddit}/submitted/top.json"
            else: # usernew
                url = f"https://www.reddit.com/user/{subreddit}/submitted/new.json"

            params = {
                "limit": batch_size,
                "after": after,
                "raw_json": 1,
                "t": time_filter,
            }

            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                logging.info("Post fetch request successful for %s", url)
            except requests.RequestException as e:
                logging.error("Post fetch request unsuccessful for %s: %s", url, e)
                break

            try:
                data = response.json()
                posts = data.get("data", {}).get("children", [])
                if not posts:
                    break

                for post in posts:
                    post_data = post["data"]
                    # Extract standard fields
                    post_info = {
                        "title": post_data["title"],
                        "author": post_data["author"],
                        "permalink": post_data["permalink"],
                        "score": post_data["score"],
                        "num_comments": post_data["num_comments"],
                        "created_utc": post_data["created_utc"],
                    }
                    # Extract media links using same priority logic as scrape_post_details
                    if post_data.get("post_hint") == "image" and "url" in post_data:
                        post_info["image_url"] = post_data["url"]
                    elif "preview" in post_data and "images" in post_data["preview"]:
                        post_info["image_url"] = post_data["preview"]["images"][0]["source"]["url"]
                    if "thumbnail" in post_data and post_data["thumbnail"] not in ["self", "default", "nsfw"]:
                        post_info["thumbnail_url"] = post_data["thumbnail"]

                    all_posts.append(post_info)
                    total_fetched += 1
                    if total_fetched >= limit:
                        break

                # Update token for pagination
                after = data["data"].get("after")
                if not after:
                    break

                time.sleep(random.uniform(1, 2))
            except (ValueError, KeyError) as e:
                logging.error("Failed to parse posts response for %s: %s", url, e)
                break

        logging.info("Successfully fetched %d posts for %s", len(all_posts), subreddit)
        return all_posts

