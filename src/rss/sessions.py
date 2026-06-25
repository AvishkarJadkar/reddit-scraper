from __future__ import annotations

from typing import Any
from requests import Session
from .agents import get_agent

"""
Session management for the RSS scraper.
Uses inheritance to automate header rotation.
"""

class RandomUserAgentSession(Session):
    """
    A requests Session subclass that automatically adds a random User-Agent header
    and full browser-like headers to every request. This helps bypass bot detection
    logic that checks for missing or inconsistent HTTP headers.
    """

    def request(self, *args: Any, **kwargs: Any) -> Any:
        """
        Overrides the base session request to inject a fresh User-Agent and
        realistic browser headers before dispatch.

        Args:
            *args: Standard requests.Session.request arguments (method, url, etc.).
            **kwargs: Standard keyword arguments (params, json, headers, etc.).

        Returns:
            Response: The HTTP response from the Reddit JSON API.
        """
        # Update session headers with a random UA and lightweight browser-like headers.
        # Reddit blocks requests missing standard Accept/Language headers, but Sec-Fetch
        # navigation headers are suspicious on a JSON API endpoint and can trigger blocks.
        self.headers.update({
            "User-Agent": get_agent(),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        })
        return super().request(*args, **kwargs)
