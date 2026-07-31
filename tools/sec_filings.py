"""Mock SEC filings MCP-style tool interface."""

from __future__ import annotations

from typing import Any


def get_recent_filings(ticker: str) -> dict[str, Any]:
    """Return fake filing metadata for scaffolded agent development."""

    return {
        "ticker": ticker.strip().upper(),
        "filings": [
            {
                "form": "10-Q",
                "filed_at": "2026-01-01",
                "summary": "Mock quarterly filing summary.",
            }
        ],
        "source": "mock",
    }

