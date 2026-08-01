"""End-to-end scaffold demo using a fake Anthropic client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.base import Agent
from agents.schema import AgentThesis
from tools.market_data import get_quote


@dataclass
class _FakeTextBlock:
    text: str


@dataclass
class _FakeResponse:
    content: list[_FakeTextBlock]


class _FakeMessages:
    def create(self, **kwargs: Any) -> _FakeResponse:
        ticker = kwargs["messages"][0]["content"].split()[-1].rstrip(".")
        return _FakeResponse(
            content=[
                _FakeTextBlock(
                    text=f"Dummy thesis for {ticker}: scaffold call path is working."
                )
            ]
        )


class _FakeAnthropicClient:
    messages = _FakeMessages()


class DummyAgent(Agent):
    agent_name = "DummyAgent"

    def build_prompt(self) -> str:
        return f"Analyze {self.ticker}."

    def parse_response(self, response: Any) -> AgentThesis:
        quote = get_quote(self.ticker)
        return AgentThesis(
            ticker=self.ticker,
            agent_name=self.agent_name,
            thesis=self.response_text(response),
            confidence=0.5,
            key_risk="This is scaffold-only output backed by mock data.",
            supporting_data={"quote": quote},
        )


def main() -> None:
    thesis = DummyAgent("AAPL", client=_FakeAnthropicClient()).analyze()
    print(thesis.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

