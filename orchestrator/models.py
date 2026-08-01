from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Signal(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


_SIGNAL_SCORE = {
    Signal.STRONG_BUY: 2,
    Signal.BUY: 1,
    Signal.HOLD: 0,
    Signal.SELL: -1,
    Signal.STRONG_SELL: -2,
}

_SCORE_SIGNAL = {v: k for k, v in _SIGNAL_SCORE.items()}


def signal_to_score(s: Signal) -> int:
    return _SIGNAL_SCORE[s]


def score_to_signal(score: float) -> Signal:
    rounded = max(-2, min(2, round(score)))
    return _SCORE_SIGNAL[rounded]


@dataclass
class AgentThesis:
    agent: str
    ticker: str
    signal: Signal
    confidence: float  # 0.0–1.0
    reasoning: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PortfolioDecision:
    ticker: str
    signal: Signal
    confidence: float
    reasoning: str
    component_theses: list[AgentThesis]


@dataclass
class FinalDecision:
    ticker: str
    signal: Signal
    confidence: float
    reasoning: str
    approved: bool
    risk_notes: str
    component_theses: list[AgentThesis]
