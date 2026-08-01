"""Mock news MCP-style tool interface."""

from __future__ import annotations

from typing import Any


def get_latest_news(ticker: str, limit: int = 5) -> dict[str, Any]:
    """Return fake news items for scaffolded agent development."""

    return {
        "ticker": ticker.strip().upper(),
        "articles": [
            {
                "headline": "Mock company update",
                "publisher": "Walsh Mock News",
                "sentiment": "neutral",
            }
            for _ in range(limit)
        ],
        "source": "mock",
    }

