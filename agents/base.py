"""Base class for all analyst agents."""
from __future__ import annotations

from abc import ABC, abstractmethod

from schema import AgentThesis


class Agent(ABC):
    """An analyst agent that turns a ticker into an AgentThesis.

    The Anthropic client is injectable so tests can pass a mock; in production
    it is created lazily on first use.
    """

    name: str = "agent"

    def __init__(self, client=None):
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import anthropic  # lazy: tests inject a mock and never import this

            self._client = anthropic.Anthropic()
        return self._client

    @abstractmethod
    def analyze(self, ticker: str) -> AgentThesis:
        ...
