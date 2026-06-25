# Reddit Scraper

> A powerful, modular Python tool for harvesting Reddit posts, comments, and media — via CLI, REST API, or programmatically.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Project Structure](#project-structure)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [CLI](#cli-usage)
  - [REST API](#rest-api-usage)
- [API Endpoints](#api-endpoints)
- [Output Format](#output-format)
- [Advanced Options](#advanced-options)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

**Reddit Scraper ** is a production-ready Python application for extracting data from Reddit's public JSON API. It handles:

- Full-text search across all of Reddit or within specific subreddits
- Deep post scraping: title, body, score, media URLs, and full nested comment trees
- Automatic pagination to retrieve thousands of results
- Media downloading (images and thumbnails)
- OCR text extraction from downloaded images (via EasyOCR)
- Date range and time-of-day filtering (in IST timezone)
- Export to structured JSON and Excel (`.xlsx`) reports

The scraper is designed with resilience in mind: it rotates User-Agent headers from a pool of 7,000+ real browser signatures and automatically retries on rate limits (`429`) and server errors.

---

## Features

| Feature | Details |
|---|---|
| **Global Search** | Searches all of Reddit by keyword with sort and time filters |
| **Subreddit Search** | Narrows search to a specific subreddit |
| **Post Details** | Fetches full post content, media links, and the recursive comment tree |
| **User Activity** | Scrapes a Redditor's posts and comments |
| **Subreddit Feed** | Fetches hot / top / new feeds from any subreddit |
| **Media Download** | Downloads full-size images and thumbnail fallbacks |
| **OCR Extraction** | Extracts visible text from downloaded images using EasyOCR |
| **Excel Export** | Generates a master `.xlsx` report with one row per comment |
| **REST API** | FastAPI server exposing all scraper functionality as HTTP endpoints |
| **Date Filtering** | Filter results by custom date range (`--start-date` / `--end-date`) |
| **Time-slot Filtering** | Filter by time of day in IST (e.g., `10:00-17:00`) |
| **UA Rotation** | Random User-Agent on every request to avoid fingerprinting |
| **Auto Retry** | Exponential backoff retry on HTTP 429/500/502/503/504 |

---

## Project Structure

```
RSS/
├── topic_harvester.py      # Main CLI entry point
├── api_runner.py           # Script to launch the FastAPI server
├── config.json             # Persistent configuration (topic, filters, limit)
├── pyproject.toml          # Project metadata and dependencies
├── harvested_data/         # Output directory (auto-created)
│   └── <topic>/
│       └── <post_title>/
│           ├── data.json       # Full post + comments in JSON
│           ├── image.jpg       # Downloaded image (if available)
│           └── thumbnail.jpg   # Fallback thumbnail (if no full image)
└── src/
    └── rs/
        ├── scraper.py      # Core RS scraper engine (RS class)
        ├── api.py          # FastAPI application and route definitions
        ├── sessions.py     # RandomUserAgentSession (UA rotation)
        ├── agents.py       # Pool of 7,000+ real browser User-Agents
        ├── ocr.py          # EasyOCR-based image text extraction
        └── utils.py        # Logging, display, media download, exports
```

---

## Architecture

```
User
 ├── CLI (topic_harvester.py)
 │    └──> RS Engine (src/rs/scraper.py)
 │              └──> RandomUserAgentSession (src/rs/sessions.py)
 │                        └──> agents.py (UA pool)
 │              └──> Reddit JSON API (reddit.com/*.json)
 │    └──> Utils (src/rs/utils.py)
 │              ├── download_image()
 │              ├── export_to_excel()
 │              └── setup_logging()
 │    └──> OCR (src/rs/ocr.py)
 │
 └── REST API (api_runner.py → src/rs/api.py)
      └──> Same RS Engine
```

The `RS` class (`src/rs/scraper.py`) is the central engine. Both the CLI and the REST API share the same scraper instance, ensuring consistent behavior across interfaces.

---

## Installation

### Prerequisites

- Python 3.10+
- [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/avishkarjadkar/reddit_scraper.git
cd reddit_scraper

# 2. Install dependencies using uv (recommended)
uv sync

# 3. (Optional) Install into a virtual environment using pip
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e .
```

> **Note:** EasyOCR will automatically download its model files on first use (~200MB). This is a one-time operation.

---

## Configuration

The `config.json` file provides persistent defaults that can be overridden by CLI arguments:

```json
{
    "topic_name": "your topic here",
    "post_type": "relevance",
    "date_of_upload": "week",
    "time_slot": "10:00-17:00",
    "limit": 5
}
```

| Key | Type | Description |
|---|---|---|
| `topic_name` | `string` | Default search keyword if none is given on the CLI |
| `post_type` | `string` | Sort order: `relevance`, `hot`, `top`, `new`, `comments` |
| `date_of_upload` | `string` | Time range: `hour`, `day`, `week`, `month`, `year`, `all` |
| `time_slot` | `string` | IST time-of-day filter in `HH:MM-HH:MM` format |
| `limit` | `int` | Number of posts to retrieve (`0` = unlimited, up to Reddit's 1000 cap) |

**Priority:** CLI argument > `config.json` > built-in default.

---

## Usage

### CLI Usage

```bash
# Basic: search and harvest 5 posts (default)
uv run topic_harvester.py "artificial intelligence"

# Custom limit and sort order
uv run topic_harvester.py "python programming" --limit 20 --sort top

# Filter by time range (posts from the last week)
uv run topic_harvester.py "climate change" --limit 10 --time week

# Filter by a custom date range
uv run topic_harvester.py "election results" --start-date 2024-11-01 --end-date 2024-11-10

# Filter by time of day in IST (posts between 10am and 5pm)
uv run topic_harvester.py "stock market" --time-slot "10:00-17:00"

# Change output directory
uv run topic_harvester.py "space exploration" --output my_data

# Use defaults from config.json (no topic argument needed)
uv run topic_harvester.py
```

**Full argument reference:**

```
usage: topic_harvester.py [-h] [--limit INT] [--sort {relevance,hot,top,new,comments}]
                          [--time {hour,day,week,month,year,all}]
                          [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
                          [--time-slot HH:MM-HH:MM] [--output DIR]
                          [topic]
```

### REST API Usage

```bash
# Start the API server
uv run api_runner.py
# Server will be available at: http://127.0.0.1:8000
# Interactive docs at:         http://127.0.0.1:8000/docs
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check and documentation link |
| `GET` | `/search` | Search Reddit by keyword |
| `GET` | `/post` | Get full post details and comment tree |
| `GET` | `/comments` | Get only the comment tree for a post |
| `GET` | `/subreddit/{name}` | Fetch a subreddit's hot/top/new feed |
| `GET` | `/user/{username}` | Get a user's recent posts and comments |

### `/search`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `q` | `string` | required | Search query |
| `limit` | `int` | `10` | Max results (1–100) |
| `sort` | `string` | `relevance` | `relevance`, `hot`, `top`, `new`, `comments` |
| `time` | `string` | `all` | `hour`, `day`, `week`, `month`, `year`, `all` |
| `time_slot` | `string` | `null` | IST time filter, e.g. `10:00-17:00` |

### `/subreddit/{name}`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | `int` | `10` | Max results (1–100) |
| `category` | `string` | `hot` | `hot`, `top`, `new`, `userhot`, `usertop`, `usernew` |
| `time` | `string` | `all` | Time range for `top` category |
| `time_slot` | `string` | `null` | IST time filter |

---

## Output Format

Each harvested post is saved in its own subfolder inside `harvested_data/<topic>/`:

```
harvested_data/
└── artificial intelligence/
    ├── AI passes bar exam with highest score/
    │   ├── data.json       ← Full post data + comments
    │   └── image.jpg       ← Downloaded image
    └── New GPT model released/
        ├── data.json
        └── thumbnail.jpg   ← Fallback if no full image
```

**`data.json` schema:**

```json
{
    "title": "Post title",
    "score": 1234,
    "created_utc": 1700000000.0,
    "body": "Post body text (if any)",
    "comments": [
        {
            "author": "username",
            "body": "Comment text",
            "score": 56,
            "replies": [ ... ]
        }
    ],
    "image_url": "https://...",
    "thumbnail_url": "https://...",
    "url": "https://...",
    "permalink": "/r/topic/comments/abc123/...",
    "image_text": "OCR-extracted text from image"
}
```

**Excel report** (`<topic>-reddit_data.xlsx`):

| Column | Description |
|---|---|
| `post` | Post title |
| `likes` | Post score (upvotes) |
| `link` | Full Reddit URL |
| `time of upload` | Timestamp in IST (YYYY-MM-DD HH:MM:SS) |
| `image_text` | Text extracted from image via OCR |
| `comments` | Comment body text |
| `comment_likes` | Comment score |
| `comment_author` | Comment author username |

> One row is generated per comment. Posts with no comments still get a single row with `[No comments]`.

---

## Advanced Options

### Proxy Support

You can pass a proxy when instantiating the `RSS` class programmatically:

```python
from src.rss.scraper import RSS

scraper = RSS(proxy="http://your-proxy:port")
results = scraper.search_reddit("your topic", limit=10)
```

### Unlimited Results

Set `--limit 0` (CLI) or `limit=0` (API/code) to fetch as many results as Reddit allows (hard-capped at 1000 per listing by Reddit's API).

### Midnight-crossing Time Slots

The `--time-slot` filter supports ranges that cross midnight:

```bash
# Posts published between 10pm and 2am IST
uv run topic_harvester.py "news" --time-slot "22:00-02:00"
```

### Logging

All activity is logged to `rss.log` in the project root. The log includes:
- Search requests and result counts
- Per-post processing status
- Download success/failure
- OCR results
- Any errors or warnings

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes and add tests if applicable
4. Run pre-commit hooks: `pre-commit run --all-files`
5. Commit and push: `git push origin feature/your-feature`
6. Open a Pull Request

This project uses the following tooling enforced via pre-commit:
- **black** — code formatting
- **ruff** — linting
- **pycln** — unused import removal
- **codespell** — spell checking

---
IMP NOTE - as if now reddit has updated their API policies and will require a developer account to scrape data of reddit
---
## License

This project is licensed under the **MIT License**.

```
MIT License

Copyright (c) 2024 Avishkar Jadkar

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

> Built by [Avishkar Jadkar](https://github.com/avishkarjadkar)
