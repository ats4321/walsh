"""Base class for LLM-backed Walsh agents."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Protocol

from agents.schema import AgentThesis


class AnthropicMessagesProtocol(Protocol):
    def create(self, **kwargs: Any) -> Any:
        """Create an Anthropic message response."""


class AnthropicClientProtocol(Protocol):
    messages: AnthropicMessagesProtocol


class Agent(ABC):
    """Abstract parent for every Walsh specialist agent.

    Subclasses own prompt construction and response parsing. The base class owns
    the Anthropic call path and enforces the `AgentThesis` return contract.
    """

    agent_name: ClassVar[str] = "BaseAgent"
    default_model: ClassVar[str] = "claude-3-5-sonnet-latest"

    def __init__(
        self,
        ticker: str,
        *,
        client: AnthropicClientProtocol | None = None,
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> None:
        self.ticker = ticker.strip().upper()
        self.client = client
        self.model = model or os.getenv("ANTHROPIC_MODEL", self.default_model)
        self.max_tokens = max_tokens

    @property
    def system_prompt(self) -> str:
        return (
            "You are a Walsh trading research agent. Return concise, "
            "evidence-grounded analysis that can be parsed into AgentThesis."
        )

    def analyze(self) -> AgentThesis:
        """Call Anthropic and convert the model response into AgentThesis."""

        response = self.call_anthropic(self.build_prompt())
        thesis = self.parse_response(response)

        if not isinstance(thesis, AgentThesis):
            raise TypeError("Agent.parse_response must return AgentThesis")

        return thesis

    def call_anthropic(self, prompt: str) -> Any:
        """Send a prompt to Anthropic using the configured or injected client."""

        client = self.client or self._build_client()
        return client.messages.create(
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

    @abstractmethod
    def build_prompt(self) -> str:
        """Build the model prompt for this agent and ticker."""

    @abstractmethod
    def parse_response(self, response: Any) -> AgentThesis:
        """Convert an Anthropic response into the shared AgentThesis schema."""

