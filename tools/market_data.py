"""Mock market data MCP-style tool interface."""

from __future__ import annotations

from typing import Any


_SECTOR_BY_TICKER = {
    "AAPL": "information_technology",
    "MSFT": "information_technology",
    "NVDA": "semiconductors",
    "XOM": "energy",
    "JPM": "financials",
    "WMT": "consumer_staples",
}


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


def get_macro_context(ticker: str) -> dict[str, Any]:
    """Return fake macro data for scaffolded macro analysis."""

    normalized = ticker.strip().upper()
    sector = _SECTOR_BY_TICKER.get(normalized, "broad_market")

    return {
        "ticker": normalized,
        "quote": get_quote(normalized),
        "sector": {
            "name": sector,
            "rotation_trend": "neutral",
            "relative_strength_30d": 0.0,
        },
        "rates": {
            "fed_funds_upper_bound": 5.5,
            "ten_year_treasury_yield": 4.25,
            "yield_curve_2s10s_bps": -25,
            "policy_bias": "restrictive",
        },
        "inflation": {
            "cpi_yoy": 3.2,
            "trend": "moderating",
        },
        "index": {
            "benchmark": "SPY",
            "benchmark_return_30d": 0.0,
            "correlation_90d": 0.72,
            "beta": 1.0,
        },
        "currency": {
            "dxy_trend": "stable",
        },
        "source": "mock",
    }
