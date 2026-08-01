import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from agents.schema import AgentThesis
from agents.sentiment import SentimentAgent


def _mock_client(payload: dict) -> MagicMock:
    block = SimpleNamespace(text=json.dumps(payload))
    response = SimpleNamespace(content=[block])
    client = MagicMock()
    client.messages.create.return_value = response
    return client


def _news_payload(ticker: str = "AAPL") -> dict:
    return {
        "ticker": ticker,
        "articles": [
            {
                "headline": "Analysts lift price targets after upbeat call",
                "publisher": "Walsh Mock News",
                "sentiment": "positive",
            }
        ],
        "source": "mock",
    }


def test_sentiment_agent_normal_case(monkeypatch) -> None:
    monkeypatch.setattr("agents.sentiment.get_latest_news", lambda ticker: _news_payload(ticker))
    client = _mock_client(
        {
            "thesis": "Sentiment is constructive after positive news and analyst upgrades.",
            "confidence": 0.78,
            "key_risk": "The sample is narrow and may reverse with guidance updates.",
            "supporting_data": {
                "sentiment_label": "positive",
                "notable_news_tone": "upbeat",
                "analyst_rating_changes": ["price target increases"],
                "earnings_call_tone_shift": "more confident",
                "key_evidence": ["positive headline tone"],
            },
        }
    )

    thesis = SentimentAgent("aapl", client=client).analyze()

    assert isinstance(thesis, AgentThesis)
    assert thesis.ticker == "AAPL"
    assert thesis.agent_name == "SentimentAgent"
    assert thesis.confidence == 0.78
    assert thesis.supporting_data["sentiment_label"] == "positive"
    assert thesis.supporting_data["news"]["source"] == "mock"

    client.messages.create.assert_called_once()
    call_kwargs = client.messages.create.call_args.kwargs
    assert "upgrades and downgrades" in call_kwargs["system"]
    assert "earnings call tone shifts" in call_kwargs["system"]


def test_sentiment_agent_missing_data_case(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.sentiment.get_latest_news",
        lambda ticker: {"ticker": ticker, "articles": [], "source": "mock"},
    )
    client = MagicMock()

    thesis = SentimentAgent("zzzz", client=client).analyze()

    assert thesis.ticker == "ZZZZ"
    assert thesis.agent_name == "SentimentAgent"
    assert thesis.confidence == 0.0
    assert "No sentiment thesis available" in thesis.thesis
    assert thesis.supporting_data["news"]["articles"] == []
    client.messages.create.assert_not_called()


def test_sentiment_agent_low_confidence_case(monkeypatch) -> None:
    monkeypatch.setattr("agents.sentiment.get_latest_news", lambda ticker: _news_payload(ticker))
    client = _mock_client(
        {
            "thesis": "Sentiment is mixed because favorable news is offset by cautious tone.",
            "confidence": 0.22,
            "key_risk": "Contradictory headlines make the sentiment read fragile.",
            "supporting_data": {
                "sentiment_label": "mixed",
                "notable_news_tone": "conflicting",
                "analyst_rating_changes": ["no clear consensus change"],
                "earnings_call_tone_shift": "cautious",
                "key_evidence": ["positive article count is too low"],
            },
        }
    )

    thesis = SentimentAgent("msft", client=client).analyze()

    assert thesis.ticker == "MSFT"
    assert thesis.confidence == 0.22
    assert 0.0 <= thesis.confidence <= 1.0
    assert thesis.supporting_data["sentiment_label"] == "mixed"
    client.messages.create.assert_called_once()
