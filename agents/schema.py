"""Shared structured outputs for all Walsh agents."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentThesis(BaseModel):
    """Canonical output emitted by every Walsh agent."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    thesis: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    key_risk: str = Field(min_length=1)
    supporting_data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

