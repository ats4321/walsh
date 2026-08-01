from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from agents.macro import MacroAgent
from agents.schema import AgentThesis


class _FakeMessages:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(content=[{"type": "text", "text": json.dumps(self.payload)}])


class _FakeAnthropicClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.messages = _FakeMessages(payload)


def test_macro_agent_returns_agent_thesis_normal_case() -> None:
    client = _FakeAnthropicClient(
        {
            "thesis": "Restrictive rates are a mild headwind, but technology sector rotation is stable.",
            "confidence": 0.72,
            "key_risk": "A renewed rise in long-duration yields could pressure valuations.",
            "supporting_data": {
                "rates_view": "restrictive",
                "sector_rotation": "neutral",
            },
        }
    )

    thesis = MacroAgent("aapl", client=client).analyze()

    assert isinstance(thesis, AgentThesis)
    assert thesis.ticker == "AAPL"
    assert thesis.agent_name == "MacroAgent"
    assert thesis.confidence == 0.72
    assert thesis.supporting_data["macro_data"]["sector"]["name"] == "information_technology"
    assert thesis.supporting_data["model_supporting_data"]["rates_view"] == "restrictive"

    call = client.messages.calls[0]
    assert "interest rate environment" in call["system"]
    assert "sector rotation" in call["system"]
    assert "correlation" in call["system"]
    assert "AAPL" in call["messages"][0]["content"]


def test_macro_agent_handles_missing_market_data(monkeypatch) -> None:
    def _missing_macro_context(ticker: str) -> dict[str, Any]:
        return {"ticker": ticker, "source": "mock", "sector": {}, "rates": {}, "index": {}}

    monkeypatch.setattr("agents.macro.get_macro_context", _missing_macro_context)
    client = _FakeAnthropicClient(
        {
            "thesis": "Macro data is too sparse to identify a durable tailwind or headwind.",
            "confidence": 0.2,
            "key_risk": "Missing rates, sector rotation, and index correlation fields.",
            "supporting_data": {"data_quality": "missing"},
        }
    )

    thesis = MacroAgent("xyz", client=client).analyze()

    assert thesis.ticker == "XYZ"
    assert thesis.confidence == 0.2
    assert thesis.supporting_data["macro_data"]["rates"] == {}
    assert thesis.supporting_data["model_supporting_data"]["data_quality"] == "missing"
    assert "lower confidence" in client.messages.calls[0]["messages"][0]["content"]


def test_macro_agent_preserves_low_confidence_response() -> None:
    client = _FakeAnthropicClient(
        {
            "thesis": "Conflicting macro signals leave no strong directional view.",
            "confidence": 0.08,
            "key_risk": "The macro regime could shift before sector data confirms a trend.",
            "supporting_data": {"signal_quality": "low"},
        }
    )

    thesis = MacroAgent("jpm", client=client).analyze()

    assert thesis.ticker == "JPM"
    assert thesis.confidence == 0.08
    assert thesis.key_risk.startswith("The macro regime")
    assert thesis.supporting_data["macro_data"]["sector"]["name"] == "financials"
