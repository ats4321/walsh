"""Shared schema for analyst agent output."""
from __future__ import annotations

from dataclasses import dataclass, field

RATINGS = ("buy", "hold", "sell")


@dataclass
class AgentThesis:
    ticker: str
    rating: str
    confidence: float  # 0.0-1.0
    summary: str
    key_points: list[str] = field(default_factory=list)
    agent: str = "agent"

    def __post_init__(self) -> None:
        self.rating = self.rating.lower()
        if self.rating not in RATINGS:
            raise ValueError(f"rating must be one of {RATINGS}, got {self.rating!r}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        if not self.ticker:
            raise ValueError("ticker is required")

    @classmethod
    def from_dict(cls, d: dict) -> "AgentThesis":
        # ponytail: pull only known keys; extras are ignored rather than exploding
        return cls(
            ticker=d["ticker"],
            rating=d["rating"],
            confidence=float(d["confidence"]),
            summary=d["summary"],
            key_points=list(d.get("key_points", [])),
            agent=d.get("agent", "agent"),
        )
