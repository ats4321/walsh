import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from agents.schema import AgentThesis
from agents.technical import TechnicalAnalyst


def _mock_client(payload: dict) -> MagicMock:
    block = SimpleNamespace(text=json.dumps(payload))
    response = SimpleNamespace(content=[block])
    client = MagicMock()
    client.messages.create.return_value = response
    return client


def _mock_market_data(monkeypatch, prices: list[float] | None = None) -> None:
    prices = prices or [90.0 + index for index in range(60)]
    monkeypatch.setattr(
        "agents.technical.market_data.get_quote",
        lambda ticker: {
            "ticker": ticker,
            "price": prices[-1],
            "change_percent": 1.4,
            "volume": 2_500_000,
            "source": "test",
        },
    )
    monkeypatch.setattr(
        "agents.technical.market_data.get_price_history",
        lambda ticker, days=90: {
            "ticker": ticker,
            "days": days,
            "prices": prices,
            "source": "test",
        },
    )


def test_technical_analyst_normal_case(monkeypatch) -> None:
    _mock_market_data(monkeypatch)
    client = _mock_client(
        {
            "thesis": "AAPL is in an improving uptrend with price above key averages.",
            "confidence": 0.78,
            "key_risk": "A volume fade near resistance could invalidate momentum.",
            "supporting_data": {
                "trend": "uptrend",
                "resistance_level": 149.0,
            },
        }
    )

    thesis = TechnicalAnalyst("aapl", client=client).analyze()

    assert isinstance(thesis, AgentThesis)
    assert thesis.ticker == "AAPL"
    assert thesis.agent_name == "TechnicalAnalyst"
    assert thesis.confidence == 0.78
    assert thesis.supporting_data["trend"] == "uptrend"
    assert thesis.supporting_data["data_available"] is True
    assert thesis.supporting_data["market_data"]["technical_signals"]["sma_20"] == 139.5
    client.messages.create.assert_called_once()
    assert "moving averages" in client.messages.create.call_args.kwargs["system"]


def test_technical_analyst_missing_data_case(monkeypatch) -> None:
    monkeypatch.setattr("agents.technical.market_data.get_quote", lambda ticker: None)
    monkeypatch.setattr(
        "agents.technical.market_data.get_price_history",
        lambda ticker, days=90: {"ticker": ticker, "days": days, "prices": []},
    )
    client = MagicMock()

    thesis = TechnicalAnalyst("zzzz", client=client).analyze()

    assert thesis.ticker == "ZZZZ"
    assert thesis.agent_name == "TechnicalAnalyst"
    assert thesis.confidence == 0.0
    assert "No usable price history" in thesis.thesis
    assert thesis.supporting_data["data_available"] is False
    client.messages.create.assert_not_called()


def test_technical_analyst_low_confidence_case(monkeypatch) -> None:
    _mock_market_data(monkeypatch, prices=[100.0, 102.0, 99.0, 101.0, 100.5])
    client = _mock_client(
        {
            "thesis": "Signals are mixed, with little directional edge.",
            "confidence": 0.18,
            "key_risk": "Whipsaw price action can quickly reverse the setup.",
            "supporting_data": {
                "trend": "sideways",
                "momentum": "mixed",
            },
        }
    )

    thesis = TechnicalAnalyst("msft", client=client).analyze()

    assert thesis.ticker == "MSFT"
    assert thesis.confidence == 0.18
    assert 0.0 <= thesis.confidence <= 1.0
    assert thesis.supporting_data["trend"] == "sideways"
    assert thesis.supporting_data["market_data"]["technical_signals"]["sma_20"] is None
    client.messages.create.assert_called_once()
