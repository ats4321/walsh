"""Fundamental Analyst agent."""
from __future__ import annotations

import json

from agents.base import Agent
from schema import AgentThesis
from tools.sec_filings import fetch_financials

SYSTEM_PROMPT = """You are a fundamental equity analyst. Given a company's \
financial data, assess it across three lenses and issue an investment thesis:

1. Valuation multiples — is the stock cheap or expensive vs. its fundamentals \
(P/E, EV/EBITDA, price-to-book relative to growth and quality)?
2. Balance sheet health — leverage (debt-to-equity), liquidity (current ratio), \
and the durability of the capital structure.
3. Earnings quality — margins, free cash flow conversion, and how much of \
reported earnings is backed by cash.

Weigh these together into a single rating (buy, hold, or sell) with a calibrated \
confidence in [0, 1]. Be skeptical: thin data or conflicting signals should lower \
confidence. Ground every point in the numbers provided."""

# ponytail: schema omits ticker/agent — the caller sets those, not the model.
# Numeric bounds on confidence are enforced in AgentThesis, not here (json_schema
# does not support numeric constraints).
_THESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "rating": {"type": "string", "enum": ["buy", "hold", "sell"]},
        "confidence": {"type": "number"},
        "summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["rating", "confidence", "summary", "key_points"],
    "additionalProperties": False,
}


class FundamentalAnalyst(Agent):
    name = "fundamental"

    def analyze(self, ticker: str) -> AgentThesis:
        ticker = ticker.strip().upper()
        data = fetch_financials(ticker)
        if not data:
            return AgentThesis(
                ticker=ticker,
                rating="hold",
                confidence=0.0,
                summary=f"No SEC filing data available for {ticker}; cannot form a thesis.",
                key_points=[],
                agent=self.name,
            )

        resp = self.client.messages.create(
            model="claude-opus-4-8",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Analyze {ticker} ({data.get('name', ticker)}). "
                        f"Financial data:\n{json.dumps(data, indent=2)}"
                    ),
                }
            ],
            output_config={"format": {"type": "json_schema", "schema": _THESIS_SCHEMA}},
        )

        text = next(b.text for b in resp.content if b.type == "text")
        payload = json.loads(text)
        payload["ticker"] = ticker
        payload["agent"] = self.name
        return AgentThesis.from_dict(payload)
