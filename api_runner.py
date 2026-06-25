import uvicorn
import os
import sys

"""
API Runner for Reddit Scraper (RSS).
Starts a Uvicorn server to host the FastAPI application.
"""

# 1. Path Manipulation:
# Ensure the 'src' directory is in the Python path so we can import 
# the 'rss' package regardless of current working directory.
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

if __name__ == "__main__":
    # Start the server on localhost:8000
    # reload=True is enabled for development ease
    print("Starting RSS API (Reddit Scraper)...")
    print("Documentation available at http://127.0.0.1:8000/docs")
    
    # Import string 'rss.api:app' tells uvicorn where to find the 'app' object
    uvicorn.run("rss.api:app", host="127.0.0.1", port=8000, reload=True)
