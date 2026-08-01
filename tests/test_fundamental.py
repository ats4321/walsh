import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agents.fundamental import FundamentalAnalyst
from schema import AgentThesis


def _mock_client(payload: dict) -> MagicMock:
    """A client whose messages.create returns a response carrying `payload` as JSON."""
    block = SimpleNamespace(type="text", text=json.dumps(payload))
    resp = SimpleNamespace(content=[block])
    client = MagicMock()
    client.messages.create.return_value = resp
    return client


def test_normal_case():
    client = _mock_client(
        {
            "rating": "buy",
            "confidence": 0.82,
            "summary": "Strong margins and cash flow at a fair multiple.",
            "key_points": ["44% gross margin", "P/E in line with peers"],
        }
    )
    thesis = FundamentalAnalyst(client=client).analyze("AAPL")

    assert isinstance(thesis, AgentThesis)
    assert thesis.ticker == "AAPL"
    assert thesis.rating == "buy"
    assert thesis.confidence == 0.82
    assert thesis.agent == "fundamental"
    assert thesis.key_points
    client.messages.create.assert_called_once()


def test_missing_data_case(monkeypatch):
    # Ticker with no filing data -> thesis without calling the API.
    monkeypatch.setattr("agents.fundamental.fetch_financials", lambda t: None)
    client = MagicMock()

    thesis = FundamentalAnalyst(client=client).analyze("ZZZZ")

    assert thesis.ticker == "ZZZZ"
    assert thesis.rating == "hold"
    assert thesis.confidence == 0.0
    assert "No SEC filing data" in thesis.summary
    client.messages.create.assert_not_called()


def test_low_confidence_case():
    client = _mock_client(
        {
            "rating": "hold",
            "confidence": 0.15,
            "summary": "Conflicting signals; thin conviction.",
            "key_points": ["High leverage offsets decent margins"],
        }
    )
    thesis = FundamentalAnalyst(client=client).analyze("KO")

    assert thesis.rating == "hold"
    assert thesis.confidence == 0.15
    assert 0.0 <= thesis.confidence <= 1.0


def test_rejects_out_of_range_confidence():
    # Guard: schema validation catches a bad model response.
    client = _mock_client(
        {"rating": "buy", "confidence": 1.5, "summary": "x", "key_points": []}
    )
    with pytest.raises(ValueError):
        FundamentalAnalyst(client=client).analyze("AAPL")
