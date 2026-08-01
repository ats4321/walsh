"""Mock market data MCP-style tool interface."""

from __future__ import annotations

from typing import Any


def get_quote(ticker: str) -> dict[str, Any]:
    """Return fake quote data for scaffolded agent development."""

    return {
        "ticker": ticker.strip().upper(),
        "price": 100.0,
        "change_percent": 0.0,
        "volume": 1_000_000,
        "source": "mock",
    }


def get_price_history(ticker: str, days: int = 30) -> dict[str, Any]:
    """Return fake price history metadata."""

    return {
        "ticker": ticker.strip().upper(),
        "days": days,
        "prices": [100.0 for _ in range(days)],
        "source": "mock",
    }
