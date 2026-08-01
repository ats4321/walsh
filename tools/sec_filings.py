"""SEC filings tool interface (mock data).

ponytail: mock data for now. Swap fetch_financials' body for a real EDGAR call
(https://www.sec.gov/cgi-bin/browse-edgar) when live data is needed — the return
shape (dict or None) is the contract callers depend on.
"""

from __future__ import annotations

from typing import Any

# Latest-annual snapshot per ticker. Numbers are illustrative.
_MOCK = {
    "AAPL": {
        "name": "Apple Inc.",
        "pe_ratio": 29.5,
        "ev_ebitda": 22.1,
        "price_to_book": 46.0,
        "debt_to_equity": 1.5,
        "current_ratio": 0.98,
        "gross_margin": 0.44,
        "net_margin": 0.25,
        "fcf_millions": 99584,
        "revenue_growth_yoy": 0.02,
    },
    "KO": {
        "name": "The Coca-Cola Company",
        "pe_ratio": 24.0,
        "ev_ebitda": 18.5,
        "price_to_book": 9.8,
        "debt_to_equity": 1.6,
        "current_ratio": 1.13,
        "gross_margin": 0.59,
        "net_margin": 0.23,
        "fcf_millions": 9747,
        "revenue_growth_yoy": 0.03,
    },
}


def fetch_financials(ticker: str) -> dict | None:
    """Return fundamental data for a ticker, or None if unavailable."""
    return _MOCK.get(ticker.strip().upper())


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
