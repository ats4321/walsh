"""Named agent placeholders for the Walsh research workflow."""

from __future__ import annotations

from typing import Any

from agents.base import Agent
from agents.schema import AgentThesis


class ScaffoldAgent(Agent):
    """Placeholder agent that documents the subclass contract."""

    agent_name = "ScaffoldAgent"

    def build_prompt(self) -> str:
        return f"Analyze {self.ticker}."

    def parse_response(self, response: Any) -> AgentThesis:
        raise NotImplementedError("Concrete agents must parse responses into AgentThesis.")


class FundamentalAgent(ScaffoldAgent):
    agent_name = "FundamentalAgent"


class TechnicalAgent(ScaffoldAgent):
    agent_name = "TechnicalAgent"


class SentimentAgent(ScaffoldAgent):
    agent_name = "SentimentAgent"


class MacroAgent(ScaffoldAgent):
    agent_name = "MacroAgent"


class RiskManagerAgent(ScaffoldAgent):
    agent_name = "RiskManagerAgent"


class PortfolioManagerAgent(ScaffoldAgent):
    agent_name = "PortfolioManagerAgent"

