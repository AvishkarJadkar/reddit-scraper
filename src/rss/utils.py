import csv
import datetime
import json
import logging
import os
from typing import Any, Dict, List, Optional, Union
from zoneinfo import ZoneInfo

import requests
from pygments import formatters, highlight, lexers
from urllib.parse import urlparse

"""
Utility functions for the Reddit Scraper (RSS).
Includes logging, colorful console display, media downloading, and data exports.
"""

def setup_logging(log_file: str = "rss.log", verbose: bool = False) -> None:
    """
    Sets up the logging configuration for the application.
    Configures both file and console handlers.

    Args:
        log_file (str): The path to the log file. Defaults to "rss.log".
        verbose (bool): If True, sets level to DEBUG. Otherwise INFO.
    """
    root_logger = logging.getLogger()
    # Set global threshold
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Remove existing handlers to avoid duplicate output if re-initialized
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Standard format: [Timestamp] - [Level] - [Message]
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # 1. File Handler: Logs everything to a persistent file
    try:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not initialize file logging: {e}")

    # 2. Console Handler: Logs to the standard output
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    logging.info("Logging initialized. Log file: %s", os.path.abspath(log_file))


def display_results(results: Union[List[Any], Dict[str, Any]], title: str) -> None:
    """
    Displays results in a formatted, colorful JSON representation in the console.
    Useful for interactive debugging or viewing harvested items.

    Args:
        results (Union[List[Any], Dict[str, Any]]): Data to be colorized.
        title (str): Header text for the display block.
    """
    try:
        print(f"\n{'-'*20} {title} {'-'*20}")

        if isinstance(results, list):
            # Iterate and print each individual item in a list
            for item in results:
                if isinstance(item, dict):
                    # Use Pygments to add terminal color-coding to JSON
                    formatted_json = json.dumps(item, sort_keys=True, indent=4)
                    colorful_json = highlight(
                        formatted_json,
                        lexers.JsonLexer(),
                        formatters.TerminalFormatter(),
                    )
                    print(colorful_json)
                else:
                    print(item)
        elif isinstance(results, dict):
            # Print a single dictionary
            formatted_json = json.dumps(results, sort_keys=True, indent=4)
            colorful_json = highlight(
                formatted_json, lexers.JsonLexer(), formatters.TerminalFormatter()
            )
            print(colorful_json)
        else:
            logging.warning("No results to display (unsupported type: %s)", type(results))
            print("No results to display.")

    except Exception as e:
        logging.error("Error displaying results: %s", e)
        print("Error displaying results.")


def download_image(
    image_url: str,
    output_folder: str = "images",
    session: Optional[requests.Session] = None,
    name: Optional[str] = None,
) -> Optional[str]:
    """
    Downloads an image from a URL and saves it to a local folder.

    Args:
        image_url (str): The source URL.
        output_folder (str): Directory where the image will be saved.
        session (Optional[requests.Session]): Reuse an existing session/RandomUserAgentSession.
        name (Optional[str]): Custom filename. If None, derives from the URL path.

    Returns:
        Optional[str]: Absolute path to the saved file, or None if failed.
    """
    os.makedirs(output_folder, exist_ok=True)

    # Resolve filename
    if name:
        filename = name
    else:
        # Extract filename from URL (e.g. image.png)
        filename = os.path.basename(urlparse(image_url).path)
        if not filename:
            filename = "downloaded_image.jpg"

    filepath = os.path.join(output_folder, filename)

    # Use specified session or fall back to standard requests
    if session is None:
        session = requests.Session()
        # Add a default User-Agent if none exists to avoid 403s
        if 'User-Agent' not in session.headers:
            session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

    try:
        # stream=True ensures we don't load huge images entirely into memory at once
        # Ensure we use session.get to inherit headers/proxies
        response = session.get(image_url, stream=True, timeout=15)
        response.raise_for_status()
        
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(8192): # Iterate in 8KB chunks
                f.write(chunk)
                
        logging.info("Downloaded media: %s", filepath)
        return os.path.abspath(filepath)
    except requests.RequestException as e:
        logging.error("Failed to download image from %s: %s", image_url, e)
        return None
    except Exception as e:
        logging.error("Unexpected error saving image %s: %s", filepath, e)
        return None


def export_to_json(data: Any, filename: str = "output.json") -> None:
    """
    Exports arbitrary data structures to a formatted JSON file.

    Args:
        data (Any): Python object (must be JSON serializable).
        filename (str): Target path.
    """
    try:
        with open(filename, "w", encoding="utf-8") as json_file:
            json.dump(data, json_file, indent=4, ensure_ascii=False)
        print(f"Data successfully exported to JSON: {filename}")
    except Exception as e:
        logging.error("Error exporting to JSON: %s", e)


def export_to_csv(data: List[Dict[str, Any]], filename: str = "output.csv") -> None:
    """
    Exports a list of flat dictionaries to a CSV file.

    Args:
        data (List[Dict[str, Any]]): List of row dictionaries.
        filename (str): Target path.
    """
    try:
        if not data:
            logging.warning("No data provided; skipping CSV export.")
            return
            
        # Extract headers from the keys of the first dictionary
        keys = data[0].keys()
        
        with open(filename, "w", newline="", encoding="utf-8") as output_file:
            dict_writer = csv.DictWriter(output_file, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(data)
            
        print(f"Data successfully exported to CSV: {filename}")
    except Exception as e:
        logging.error("Error exporting to CSV: %s", e)


def export_to_excel(all_post_details: List[Dict[str, Any]], filename: str = "report.xlsx") -> None:
    """
    Exports harvested Reddit data to an Excel file with the structure requested by the user.
    One row is created for each comment, repeating the post information.

    Structure:
    - post (Title)
    - likes (Post Score)
    - link (Post Link)
    - time of upload (IST)
    - comments (Comment Body)
    - comment_likes (Comment Score)
    - comment_author (Comment Author)

    Args:
        all_post_details (List[Dict[str, Any]]): List of dictionaries containing post and nested comment data.
        filename (str): Target path for the Excel file.
    """
    try:
        import pandas as pd
        
        flat_rows = []

        # Try to load IST timezone, fallback to manual offset if tzdata is missing
        try:
            ist_tz = ZoneInfo("Asia/Kolkata")
        except Exception:
            ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

        def flatten_comments(comments_list, post_info, ist_time_str):
            """Recursive helper to flatten the comment tree into rows."""
            for comment in comments_list:
                row = {
                    "post": post_info.get("title"),
                    "likes": post_info.get("score"),
                    "link": f"https://www.reddit.com{post_info.get('permalink')}",
                    "time of upload": ist_time_str,
                    "image_text": post_info.get("image_text", ""),
                    "comments": comment.get("body"),
                    "comment_likes": comment.get("score"),
                    "comment_author": comment.get("author")
                }
                flat_rows.append(row)
                
                # Process nested replies
                if comment.get("replies"):
                    flatten_comments(comment["replies"], post_info, ist_time_str)

        # Process each post
        for post in all_post_details:
            if not post:
                continue
            
            # Format the IST time string
            created_utc = post.get("created_utc")
            ist_time_str = "N/A"
            if created_utc:
                dt_utc = datetime.datetime.fromtimestamp(created_utc, tz=datetime.timezone.utc)
                dt_ist = dt_utc.astimezone(ist_tz)
                ist_time_str = dt_ist.strftime("%Y-%m-%d %H:%M:%S")

            # If there are no comments, add at least one row for the post itself
            if not post.get("comments"):
                flat_rows.append({
                    "post": post.get("title"),
                    "likes": post.get("score"),
                    "link": f"https://www.reddit.com{post.get('permalink')}",
                    "time of upload": ist_time_str,
                    "image_text": post.get("image_text", ""),
                    "comments": "[No comments]",
                    "comment_likes": 0,
                    "comment_author": "N/A"
                })
            else:
                flatten_comments(post["comments"], post, ist_time_str)

        # Create DataFrame and export
        df = pd.DataFrame(flat_rows)
        
        # Reorder columns to match user request exactly
        cols = ["post", "likes", "link", "time of upload", "image_text", "comments", "comment_likes", "comment_author"]
        df = df[cols]
        
        df.to_excel(filename, index=False, engine='openpyxl')
        logging.info("Excel report generated successfully: %s", os.path.abspath(filename))
        print(f"Excel report successfully generated: {os.path.abspath(filename)}")

    except ImportError:
        logging.error("Failed to export to Excel: 'pandas' and 'openpyxl' are required. Please install them.")
    except Exception as e:
        logging.error("Error exporting to Excel: %s", e)
