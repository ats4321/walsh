"""Technical Analyst agent."""

from __future__ import annotations

import json
from typing import Any

from agents.base import Agent
from agents.schema import AgentThesis
from tools import market_data


class TechnicalAnalyst(Agent):
    """LLM-backed analyst for price action, trend, momentum, volume, and levels."""

    agent_name = "TechnicalAnalyst"

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Walsh Technical Analyst. Analyze price and volume "
            "patterns, moving averages, momentum indicators, and likely "
            "support/resistance levels. Be concise, quantify signal strength, "
            "lower confidence when data is thin or signals conflict, and return "
            "only JSON with keys: thesis, confidence, key_risk, supporting_data."
        )

    def analyze(self) -> AgentThesis:
        """Fetch market data, then call Anthropic only when usable data exists."""

        self._market_snapshot = self._fetch_market_snapshot()
        if not self._has_usable_market_data(self._market_snapshot):
            return AgentThesis(
                ticker=self.ticker,
                agent_name=self.agent_name,
                thesis=(
                    f"No usable price history is available for {self.ticker}; "
                    "technical conviction is unavailable."
                ),
                confidence=0.0,
                key_risk="Insufficient market data for trend, momentum, or levels.",
                supporting_data={
                    "market_data": self._market_snapshot,
                    "data_available": False,
                },
            )

        response = self.call_anthropic(self.build_prompt())
        thesis = self.parse_response(response)

        if not isinstance(thesis, AgentThesis):
            raise TypeError("TechnicalAnalyst.parse_response must return AgentThesis")

        return thesis

    def build_prompt(self) -> str:
        snapshot = getattr(self, "_market_snapshot", None)
        if snapshot is None:
            snapshot = self._fetch_market_snapshot()
            self._market_snapshot = snapshot

        return (
            f"Analyze {self.ticker} using this market data and technical signal "
            "snapshot. Focus on trend, price/volume confirmation, moving "
            "averages, momentum, and support/resistance. Return strict JSON "
            "matching this shape: "
            '{"thesis": str, "confidence": float, "key_risk": str, '
            '"supporting_data": object}.\n\n'
            f"{json.dumps(snapshot, indent=2, sort_keys=True)}"
        )

    def parse_response(self, response: Any) -> AgentThesis:
        payload = self._load_json_response(response)
        supporting_data = dict(payload.get("supporting_data") or {})
        supporting_data["market_data"] = getattr(
            self, "_market_snapshot", self._fetch_market_snapshot()
        )
        supporting_data["data_available"] = True

        return AgentThesis(
            ticker=self.ticker,
            agent_name=self.agent_name,
            thesis=payload["thesis"],
            confidence=payload["confidence"],
            key_risk=payload["key_risk"],
            supporting_data=supporting_data,
        )

    def _fetch_market_snapshot(self) -> dict[str, Any]:
        quote = market_data.get_quote(self.ticker)
        history = market_data.get_price_history(self.ticker, days=90)
        prices = self._numeric_series((history or {}).get("prices", []))

        return {
            "quote": quote,
            "price_history": history,
            "technical_signals": self._technical_signals(quote or {}, prices),
        }

    def _has_usable_market_data(self, snapshot: dict[str, Any]) -> bool:
        history = snapshot.get("price_history") or {}
        prices = self._numeric_series(history.get("prices", []))
        return bool(snapshot.get("quote")) and len(prices) >= 2

    def _technical_signals(
        self, quote: dict[str, Any], prices: list[float]
    ) -> dict[str, Any]:
        last_price = quote.get("price") if quote else None
        if last_price is None and prices:
            last_price = prices[-1]

        return {
            "last_price": last_price,
            "sma_20": self._sma(prices, 20),
            "sma_50": self._sma(prices, 50),
            "momentum_10d_percent": self._momentum_percent(prices, 10),
            "support_20d": min(prices[-20:]) if prices else None,
            "resistance_20d": max(prices[-20:]) if prices else None,
            "latest_volume": quote.get("volume") if quote else None,
        }

    def _load_json_response(self, response: Any) -> dict[str, Any]:
        text = self.response_text(response).strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("Anthropic response must be a JSON object")

        return payload

    def _numeric_series(self, values: Any) -> list[float]:
        if not isinstance(values, list):
            return []

        series: list[float] = []
        for value in values:
            if isinstance(value, (int, float)):
                series.append(float(value))
        return series

    def _sma(self, prices: list[float], window: int) -> float | None:
        if len(prices) < window:
            return None
        return round(sum(prices[-window:]) / window, 4)

    def _momentum_percent(self, prices: list[float], periods: int) -> float | None:
        if len(prices) <= periods:
            return None

        previous = prices[-periods - 1]
        if previous == 0:
            return None

        return round(((prices[-1] - previous) / previous) * 100, 4)


TechnicalAgent = TechnicalAnalyst
