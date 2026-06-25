# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests",
#     "pygments",
# ]
# ///

"""
Reddit Scraper (RSS) CLI.

This script allows users to search for and download Reddit posts and their media
based on a topic or keyword, with support for date ranges and sorting.
"""

import argparse
import datetime
import json
import logging
import os
import random
import re
import sys
import time
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

# Import internal modules, handling paths for different execution environments
try:
    from src.rss.utils import download_image, setup_logging, export_to_excel
    from src.rss.scraper import RSS
except ImportError:
    # Fallback to local import if run from a different context
    sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
    from rss.utils import download_image, setup_logging, export_to_excel
    from rss.scraper import RSS


def sanitize_filename(name: str) -> str:
    """
    Sanitize a string to be safe for filenames by removing invalid characters.

    Args:
        name (str): The string to sanitize.

    Returns:
        str: The sanitized string, truncated to 50 characters.
    """
    # Remove characters that are illegal in Windows/Linux filenames
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()[:50]


def main() -> None:
    """
    Main entry point for the Reddit Scraper (RSS) CLI.
    
    Handles argument parsing, configuration loading, Reddit searching,
    result filtering (date/time), and data extraction (JSON + Media).
    """
    # 1. Argument Parsing
    parser = argparse.ArgumentParser(description="RSS - Reddit Scraper. Harvest Reddit posts based on topic/keyword.")
    parser.add_argument("topic", nargs="?", help="The topic or keyword to search for.")
    parser.add_argument("--limit", type=int, default=5, help="Number of posts to retrieve (default: 5).")
    parser.add_argument(
        "--sort",
        choices=["relevance", "hot", "top", "new", "comments"],
        default="relevance",
        help="Sort order for search results.",
    )
    parser.add_argument(
        "--time",
        choices=["hour", "day", "week", "month", "year", "all"],
        default="all",
        help="Time filter for search results.",
    )
    parser.add_argument("--start-date", help="Start date for custom range (YYYY-MM-DD).")
    parser.add_argument("--end-date", help="End date for custom range (YYYY-MM-DD).")
    parser.add_argument("--time-slot", help="Filter by time of day (e.g., 10:00-12:00 in UTC).")
    parser.add_argument("--output", default="harvested_data", help="Output directory (default: harvested_data).")

    args = parser.parse_args()
    
    # Initialize Logging
    setup_logging()

    # 2. Configuration Loading
    config = {}
    config_path = "config.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                logging.info("Loaded configuration from %s", config_path)
        except Exception as e:
            logging.error("Error reading %s: %s", config_path, e)

    # Initialize the Scraper Engine
    miner = RSS()

    # 3. Parameter Evaluation (Priority: CLI > Config > Default)
    topic = args.topic if args.topic else config.get("topic_name")
    if not topic:
        logging.error("No topic provided. Please specify a topic as an argument or in config.json.")
        return

    sort_order = args.sort if args.sort != "relevance" else config.get("post_type", "relevance")
    time_filter = args.time if args.time != "all" else config.get("date_of_upload", "all")
    time_slot_str = args.time_slot if args.time_slot else config.get("time_slot")
    
    # Accept 0 as "unlimited" results
    limit = args.limit if args.limit != 5 else config.get("limit", 5)
    limit_display = "Unlimited" if limit == 0 else str(limit)

    # 4. Date Range Parsing
    start_ts: Optional[int] = None
    end_ts: Optional[int] = None

    if args.start_date or args.end_date:
        if not (args.start_date and args.end_date):
            logging.error("Both --start-date and --end-date must be provided for a custom range.")
            return

        try:
            start_dt = datetime.datetime.strptime(args.start_date, "%Y-%m-%d")
            end_dt = datetime.datetime.strptime(args.end_date, "%Y-%m-%d")
            # Set end date to the very end of the specified day
            end_dt = end_dt.replace(hour=23, minute=59, second=59)

            start_ts = int(start_dt.timestamp())
            end_ts = int(end_dt.timestamp())

            logging.info("Filtering results between %s and %s", args.start_date, args.end_date)

        except ValueError:
            logging.error("Invalid date format. Please use YYYY-MM-DD.")
            return

    # 5. Time Slot Parsing (IST)
    slot_start: Optional[datetime.time] = None
    slot_end: Optional[datetime.time] = None

    if time_slot_str:
        try:
            start_str, end_str = time_slot_str.split("-")
            slot_start = datetime.datetime.strptime(start_str.strip(), "%H:%M").time()
            slot_end = datetime.datetime.strptime(end_str.strip(), "%H:%M").time()
            logging.info("Applying time slot filter: %s to %s (IST)", slot_start, slot_end)
        except ValueError:
            logging.error("Invalid time-slot format. Please use HH:MM-HH:MM (e.g., 10:00-12:00).")
            return

    # 6. Execute Search
    logging.info("Searching Reddit for topic: '%s' (sort: %s, time: %s)...", topic, sort_order, time_filter)
    
    # If filtering, we fetch more results than the limit to ensure we have enough matches after filtering.
    if limit == 0:
        search_limit = 0
    else:
        search_limit = limit * 10 if (start_ts or time_slot_str) else limit
        
    search_results = miner.search_reddit(topic, limit=search_limit, sort=sort_order, time_filter=time_filter)

    if not search_results:
        logging.info("No results found.")
        return

    # 7. Local Filtering (Date Range and Time Slot)
    filtered_results = []
    
    # Try to load IST timezone, fallback to manual offset if tzdata is missing
    try:
        ist_tz = ZoneInfo("Asia/Kolkata")
    except Exception:
        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        logging.warning("ZoneInfo 'Asia/Kolkata' not found. Falling back to manual UTC+5:30 offset.")
    
    for result in search_results:
        created_utc = result.get("created_utc")
        if not created_utc:
            continue
            
        # Check against custom date range
        if start_ts and end_ts:
            if not (start_ts <= created_utc <= end_ts):
                continue
        
        # Check against daily time slot (converted to IST)
        if slot_start and slot_end:
            # Convert UTC timestamp to IST time object
            post_time = datetime.datetime.fromtimestamp(created_utc, tz=datetime.timezone.utc).astimezone(ist_tz).time()
            if slot_start <= slot_end:
                if not (slot_start <= post_time <= slot_end):
                    continue
            else:  # Range crosses midnight (e.g., 22:00 to 02:00)
                if not (post_time >= slot_start or post_time <= slot_end):
                    continue
        
        filtered_results.append(result)

    # Finalize the result set based on limit
    if start_ts or time_slot_str:
        logging.info("Found %d posts, %d matches filters.", len(search_results), len(filtered_results))
        search_results = filtered_results if limit == 0 else filtered_results[:limit]
    else:
        search_results = filtered_results

    if not search_results:
        logging.info("No results found matching the specified filters.")
        return

    logging.info("Found %d posts (limit: %s). Starting extraction...", len(search_results), limit_display)

    # 8. Data Extraction and Saving
    base_output_dir = os.path.join(args.output, sanitize_filename(topic))
    os.makedirs(base_output_dir, exist_ok=True)
    
    # List to store all captured post details for the final Excel report
    all_harvested_data: List[Dict[str, Any]] = []

    for i, result in enumerate(search_results):
        try:
            logging.info("Processing post %d/%d: %s", i + 1, len(search_results), result["title"])

            # Extract permalink from the full URL for the detail scraper
            permalink = urlparse(result["link"]).path

            # Scrape deep details (body text, comments, media URLs)
            post_details = miner.scrape_post_details(permalink)

            if not post_details:
                logging.warning("  Skipping post %d (failed to scrape details)", i + 1)
                continue
            
            # Store for the final master Excel export
            all_harvested_data.append(post_details)

            # Organize into post-specific folder
            post_folder_name = sanitize_filename(post_details["title"])
            post_dir = os.path.join(base_output_dir, post_folder_name)
            os.makedirs(post_dir, exist_ok=True)

            # Download post media (preferring full-size image, then fallback to thumbnail)
            image_path = None
            if post_details.get("image_url"):
                logging.info("  Downloading image: %s", post_details["image_url"])
                image_path = download_image(post_details["image_url"], output_folder=post_dir, name="image.jpg", session=miner.session)

            if not image_path and post_details.get("thumbnail_url") and post_details.get("thumbnail_url") not in ["self", "default", "nsfw", ""]:
                logging.info("  Falling back to thumbnail: %s", post_details["thumbnail_url"])
                image_path = download_image(post_details["thumbnail_url"], output_folder=post_dir, name="thumbnail.jpg", session=miner.session)

            # Extract Text from Image (OCR)
            if image_path:
                try:
                    from src.rss.ocr import extract_text_from_image
                    extracted_text = extract_text_from_image(image_path)
                    post_details["image_text"] = extracted_text
                except Exception as e:
                     logging.error("  Error during OCR: %s", e)
                     post_details["image_text"] = ""
            else:
                 post_details["image_text"] = ""

            # Save detailed data to JSON (after OCR to include text)
            json_path = os.path.join(post_dir, "data.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(post_details, f, indent=4, ensure_ascii=False)

        except Exception as e:
            logging.error("  Error processing post %d: %s", i + 1, e)

    # 9. Master Excel Export
    if all_harvested_data:
        logging.info("Generating master Excel report...")
        # Filename format: sanitized_topic_name-reddit_data.xlsx
        report_name = f"{sanitize_filename(topic)}-reddit_data.xlsx"
        report_path = os.path.join(base_output_dir, report_name)
        export_to_excel(all_harvested_data, filename=report_path)

    # Final Summary Output
    logging.info("Extraction complete! Data saved to: %s", os.path.abspath(base_output_dir))
    
    print(f"\n{'='*50}")
    print(f"SUCCESS: Extraction complete!")
    print(f"Data location: {os.path.abspath(base_output_dir)}")
    if all_harvested_data:
        print(f"Excel report: {os.path.abspath(report_path)}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
