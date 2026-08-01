"""Base class for LLM-backed Walsh agents.

Serves two agent styles: technical-style agents pass ``ticker`` at
construction and override ``build_prompt``/``parse_response``; other agents
(e.g. fundamental) take only a client and override ``analyze(ticker)``.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Protocol


class AnthropicMessagesProtocol(Protocol):
    def create(self, **kwargs: Any) -> Any:
        """Create an Anthropic message response."""


class AnthropicClientProtocol(Protocol):
    messages: AnthropicMessagesProtocol


class Agent(ABC):
    """Abstract parent for every Walsh specialist agent."""

    agent_name: ClassVar[str] = "BaseAgent"
    default_model: ClassVar[str] = "claude-3-5-sonnet-latest"

    def __init__(
        self,
        ticker: str | None = None,
        *,
        client: AnthropicClientProtocol | None = None,
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> None:
        self.ticker = ticker.strip().upper() if ticker else ticker
        self._client = client
        self.model = model or os.getenv("ANTHROPIC_MODEL", self.default_model)
        self.max_tokens = max_tokens

    @property
    def client(self) -> AnthropicClientProtocol:
        """Injected client, or a lazily-built real Anthropic client."""

        if self._client is None:
            self._client = self._build_client()
        return self._client

    @property
    def system_prompt(self) -> str:
        return (
            "You are a Walsh trading research agent. Return concise, "
            "evidence-grounded analysis that can be parsed into AgentThesis."
        )

    @abstractmethod
    def analyze(self, *args: Any, **kwargs: Any) -> Any:
        """Produce this agent's thesis for its ticker."""

    def call_anthropic(self, prompt: str) -> Any:
        """Send a prompt to Anthropic using the configured or injected client."""

        return self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )

    def response_text(self, response: Any) -> str:
        """Extract text from common Anthropic SDK response shapes."""

        content = getattr(response, "content", response)
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text")
                else:
                    text = getattr(block, "text", None)
                if text:
                    parts.append(str(text))
            return "\n".join(parts)

        return str(content)

    def _build_client(self) -> AnthropicClientProtocol:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError(
                "The anthropic package is required for real agent calls. "
                "Install project dependencies or inject a test client."
            ) from exc

        return Anthropic()

    def build_prompt(self) -> str:
        """Build the model prompt for this agent and ticker."""
        raise NotImplementedError

    def parse_response(self, response: Any) -> Any:
        """Convert an Anthropic response into an AgentThesis."""
        raise NotImplementedError
