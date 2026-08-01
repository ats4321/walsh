"""Sentiment specialist agent for news-driven equity research."""

from __future__ import annotations

import json
from typing import Any

from agents.base import Agent
from agents.schema import AgentThesis
from tools.news import get_latest_news


class SentimentAgent(Agent):
    """Analyze market sentiment from news and analyst narrative signals."""

    agent_name = "SentimentAgent"

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Walsh Sentiment Agent, specialized in equity sentiment "
            "analysis. Evaluate news tone, analyst rating changes including "
            "upgrades and downgrades, and earnings call tone shifts. Be concise, "
            "skeptical of thin data, and return only valid JSON for AgentThesis "
            "fields: thesis, confidence, key_risk, and supporting_data."
        )

    def analyze(self) -> AgentThesis:
        """Fetch news, optionally call Anthropic, and return AgentThesis."""

        news_data = self._fetch_news_data()
        if not news_data.get("articles"):
            return AgentThesis(
                ticker=self.ticker,
                agent_name=self.agent_name,
                thesis=(
                    f"No sentiment thesis available for {self.ticker}; "
                    "the news tool returned no usable articles."
                ),
                confidence=0.0,
                key_risk="No recent news data was available for sentiment analysis.",
                supporting_data={"news": news_data},
            )

        return super().analyze()

    def build_prompt(self) -> str:
        news_data = self._fetch_news_data()
        return (
            f"Analyze sentiment for {self.ticker} using this news payload:\n"
            f"{json.dumps(news_data, indent=2, sort_keys=True)}\n\n"
            "Return exactly one JSON object with these fields:\n"
            '- "thesis": a concise sentiment thesis string\n'
            '- "confidence": a number from 0.0 to 1.0\n'
            '- "key_risk": the main risk to the sentiment read\n'
            '- "supporting_data": an object containing sentiment_label, '
            "notable_news_tone, analyst_rating_changes, earnings_call_tone_shift, "
            "and key_evidence"
        )

    def parse_response(self, response: Any) -> AgentThesis:
        payload = json.loads(self._json_text(response))
        supporting_data = dict(payload.get("supporting_data") or {})
        supporting_data.setdefault("news", self._fetch_news_data())

        return AgentThesis(
            ticker=self.ticker,
            agent_name=self.agent_name,
            thesis=str(payload["thesis"]),
            confidence=float(payload["confidence"]),
            key_risk=str(payload["key_risk"]),
            supporting_data=supporting_data,
        )

    def _fetch_news_data(self) -> dict[str, Any]:
        cached = getattr(self, "_news_data", None)
        if cached is None:
            cached = get_latest_news(self.ticker)
            self._news_data = cached or {"ticker": self.ticker, "articles": []}
        return self._news_data

    def _json_text(self, response: Any) -> str:
        text = self.response_text(response).strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text
