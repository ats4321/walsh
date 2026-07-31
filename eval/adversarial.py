"""Adversarial robustness test suite for Walsh signal agents.

Feeds deliberately ambiguous, contradictory, or degenerate inputs to each
agent type and flags cases where confidence stays high despite unreliable
input.

Usage:
    python -m eval.adversarial
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agents.schema import AgentThesis
from backtest.engine import (
    MeanReversionSignalAgent,
    MomentumSignalAgent,
    TechnicalSignalAgent,
)

RESULTS_DIR = Path(__file__).parent / "results"

OVERCONFIDENCE_THRESHOLD = 0.65  # confidence above this on bad input = flagged


# ---------------------------------------------------------------------------
# Test case structure
# ---------------------------------------------------------------------------

@dataclass
class AdversarialCase:
    case_id: str
    agent_name: str
    description: str
    prices: list[float]          # injected price history
    expect_low_confidence: bool  # True if we expect confidence < OVERCONFIDENCE_THRESHOLD
    expected_max_confidence: float = OVERCONFIDENCE_THRESHOLD


@dataclass
class AdversarialResult:
    case_id: str
    agent_name: str
    description: str
    confidence: float
    direction: int
    thesis: str
    expected_max_confidence: float
    flagged: bool    # True = overconfident on bad input (confidence > expected_max)
    crashed: bool    # True = agent raised an exception on this input
    thesis_text: str


# ---------------------------------------------------------------------------
# Adversarial price patterns
# ---------------------------------------------------------------------------

def _flat(n: int, price: float = 100.0) -> list[float]:
    return [price] * n


def _trending_up(n: int, start: float = 80.0, step: float = 0.5) -> list[float]:
    return [start + i * step for i in range(n)]


def _trending_down(n: int, start: float = 120.0, step: float = 0.5) -> list[float]:
    return [start - i * step for i in range(n)]


def _crash_then_recover(n: int) -> list[float]:
    """Strong uptrend, then sudden 20% crash, then partial recovery."""
    mid = n // 2
    up = _trending_up(mid, 80.0, 0.5)
    crash_price = up[-1] * 0.80
    down = [crash_price + i * 0.3 for i in range(n - mid)]
    return up + down


def _zigzag(n: int, base: float = 100.0, amp: float = 5.0) -> list[float]:
    """Oscillating prices with no clear trend."""
    return [base + amp * (1 if i % 2 == 0 else -1) for i in range(n)]


def _single_price(n: int = 1) -> list[float]:
    return [100.0] * n


def _zero_prices(n: int) -> list[float]:
    return [0.0] * n


def _negative_prices(n: int) -> list[float]:
    return [-100.0 + i for i in range(n)]


def _contradictory_sma(n: int) -> list[float]:
    """
    Price above SMA20 (bullish technical) but 20d momentum sharply negative.
    Achieved by: long slow uptrend, then sudden sharp drop, then bounce back above SMA.
    """
    # 50 days of slow rise
    slow_up = [100.0 + i * 0.1 for i in range(50)]
    # 10 days of sharp drop (creates negative momentum)
    drop = [slow_up[-1] - i * 2.0 for i in range(1, 11)]
    # 10 days of partial recovery (back above SMA20 but momentum still negative)
    recover = [drop[-1] + i * 1.5 for i in range(1, n - 60)]
    return slow_up + drop + recover


def _all_same_then_jump(n: int) -> list[float]:
    """n-1 days flat, then sudden 50% jump. Tests for overconfidence on tiny history."""
    return [100.0] * (n - 1) + [150.0]


# ---------------------------------------------------------------------------
# Test cases: 5+ per agent type
# ---------------------------------------------------------------------------

TECHNICAL_CASES: list[AdversarialCase] = [
    AdversarialCase(
        case_id="TECH_001",
        agent_name="TechnicalSignalAgent",
        description="Only 1 data point — no signal should be possible",
        prices=_single_price(1),
        expect_low_confidence=True,
        expected_max_confidence=0.4,
    ),
    AdversarialCase(
        case_id="TECH_002",
        agent_name="TechnicalSignalAgent",
        description="All prices identical — zero variance, no trend",
        prices=_flat(60),
        expect_low_confidence=True,
        expected_max_confidence=0.65,
    ),
    AdversarialCase(
        case_id="TECH_003",
        agent_name="TechnicalSignalAgent",
        description="Zigzag prices — mixed signals, should not be highly confident",
        prices=_zigzag(60),
        expect_low_confidence=True,
        expected_max_confidence=0.65,
    ),
    AdversarialCase(
        case_id="TECH_004",
        agent_name="TechnicalSignalAgent",
        description="Sharp crash after uptrend — contradicts prior bullish signals",
        prices=_crash_then_recover(70),
        expect_low_confidence=True,
        expected_max_confidence=0.65,
    ),
    AdversarialCase(
        case_id="TECH_005",
        agent_name="TechnicalSignalAgent",
        description="Contradictory: price above SMA but sharp negative momentum",
        prices=_contradictory_sma(70),
        expect_low_confidence=True,
        expected_max_confidence=0.65,
    ),
    AdversarialCase(
        case_id="TECH_006",
        agent_name="TechnicalSignalAgent",
        description="Single day 50% jump after flat history — spurious signal",
        prices=_all_same_then_jump(30),
        expect_low_confidence=True,
        expected_max_confidence=0.75,
    ),
]

MOMENTUM_CASES: list[AdversarialCase] = [
    AdversarialCase(
        case_id="MOM_001",
        agent_name="MomentumSignalAgent",
        description="Only 5 data points — far below 63d lookback, no signal",
        prices=_single_price(5),
        expect_low_confidence=True,
        expected_max_confidence=0.4,
    ),
    AdversarialCase(
        case_id="MOM_002",
        agent_name="MomentumSignalAgent",
        description="Flat prices — zero momentum, direction meaningless",
        prices=_flat(120),
        expect_low_confidence=True,
        expected_max_confidence=0.5,
    ),
    AdversarialCase(
        case_id="MOM_003",
        agent_name="MomentumSignalAgent",
        description="Strong 12m momentum but negative 3m (trend reversal)",
        prices=_trending_up(200, 50.0, 0.3) + _trending_down(30, 120.0, 1.0),
        expect_low_confidence=True,
        expected_max_confidence=0.7,
    ),
    AdversarialCase(
        case_id="MOM_004",
        agent_name="MomentumSignalAgent",
        description="Zigzag for 200 days — no momentum in either direction",
        prices=_zigzag(200),
        expect_low_confidence=True,
        expected_max_confidence=0.6,
    ),
    AdversarialCase(
        case_id="MOM_005",
        agent_name="MomentumSignalAgent",
        description="Negative prices (data corruption) — should not produce confident signal",
        prices=_negative_prices(100),
        expect_low_confidence=True,
        expected_max_confidence=0.65,
    ),
    AdversarialCase(
        case_id="MOM_006",
        agent_name="MomentumSignalAgent",
        description="Crash then recover — 3m and 12m signals conflict",
        prices=_crash_then_recover(200),
        expect_low_confidence=True,
        expected_max_confidence=0.7,
    ),
]

MEANREV_CASES: list[AdversarialCase] = [
    AdversarialCase(
        case_id="REV_001",
        agent_name="MeanReversionSignalAgent",
        description="Fewer than 20 data points — too little history",
        prices=_flat(10),
        expect_low_confidence=True,
        expected_max_confidence=0.3,
    ),
    AdversarialCase(
        case_id="REV_002",
        agent_name="MeanReversionSignalAgent",
        description="All prices identical — zero range, direction undefined",
        prices=_flat(100),
        expect_low_confidence=True,
        expected_max_confidence=0.3,
    ),
    AdversarialCase(
        case_id="REV_003",
        agent_name="MeanReversionSignalAgent",
        description="Price at exact midpoint of range — neutral zone, no clear reversion",
        prices=list(range(50, 150)) + [100],  # ends at midpoint
        expect_low_confidence=True,
        expected_max_confidence=0.45,
    ),
    AdversarialCase(
        case_id="REV_004",
        agent_name="MeanReversionSignalAgent",
        description="Persistent downtrend — being near 52w low doesn't mean reversion",
        prices=_trending_down(150, 200.0, 0.8),
        expect_low_confidence=True,
        expected_max_confidence=0.85,  # ponytail: this agent legitimately signals at lows; ensure it at least doesn't hit 0.9
    ),
    AdversarialCase(
        case_id="REV_005",
        agent_name="MeanReversionSignalAgent",
        description="Zero prices — degenerate input should not produce confident signal",
        prices=_zero_prices(60),
        expect_low_confidence=True,
        expected_max_confidence=0.3,
    ),
    AdversarialCase(
        case_id="REV_006",
        agent_name="MeanReversionSignalAgent",
        description="Zigzag — mid-range, no clear reversion target",
        prices=_zigzag(100),
        expect_low_confidence=True,
        expected_max_confidence=0.5,
    ),
]

ALL_CASES: list[AdversarialCase] = TECHNICAL_CASES + MOMENTUM_CASES + MEANREV_CASES


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _get_agent(agent_name: str) -> Any:
    agents = {
        "TechnicalSignalAgent": TechnicalSignalAgent(),
        "MomentumSignalAgent": MomentumSignalAgent(),
        "MeanReversionSignalAgent": MeanReversionSignalAgent(),
    }
    return agents.get(agent_name)


def run_adversarial(
    cases: list[AdversarialCase] | None = None,
) -> list[AdversarialResult]:
    if cases is None:
        cases = ALL_CASES

    results: list[AdversarialResult] = []

    for case in cases:
        agent = _get_agent(case.agent_name)
        if agent is None:
            continue

        try:
            thesis: AgentThesis = agent.analyze("TESTX", case.prices)
        except Exception as exc:
            # Agent crashed on bad input — record as a crash (separate from overconfidence)
            results.append(
                AdversarialResult(
                    case_id=case.case_id,
                    agent_name=case.agent_name,
                    description=case.description,
                    confidence=0.0,
                    direction=0,
                    thesis="[CRASHED]",
                    expected_max_confidence=case.expected_max_confidence,
                    flagged=False,
                    crashed=True,
                    thesis_text=f"Exception: {exc}",
                )
            )
            continue

        direction = int(thesis.supporting_data.get("direction", 0))
        flagged = (
            case.expect_low_confidence
            and thesis.confidence > case.expected_max_confidence
        )

        results.append(
            AdversarialResult(
                case_id=case.case_id,
                agent_name=case.agent_name,
                description=case.description,
                confidence=thesis.confidence,
                direction=direction,
                thesis=thesis.thesis,
                expected_max_confidence=case.expected_max_confidence,
                flagged=flagged,
                crashed=False,
                thesis_text=thesis.thesis,
            )
        )

    return results


def _print_results(results: list[AdversarialResult]) -> None:
    flagged = [r for r in results if r.flagged]
    crashed = [r for r in results if r.crashed]
    print(
        f"\n=== Adversarial Tests: {len(results)} cases, "
        f"{len(flagged)} overconfident, {len(crashed)} crashed ===\n"
    )
    for r in results:
        if r.crashed:
            status = "CRASH"
        elif r.flagged:
            status = "FLAGGED"
        else:
            status = "ok"
        print(
            f"  [{status}] {r.case_id} ({r.agent_name})\n"
            f"          {r.description}\n"
            f"          confidence={r.confidence:.2f} "
            f"(max_expected={r.expected_max_confidence:.2f})\n"
        )


def save_results(results: list[AdversarialResult]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"{ts}_adversarial.json"
    out.write_text(
        json.dumps(
            [
                {
                    "case_id": r.case_id,
                    "agent_name": r.agent_name,
                    "description": r.description,
                    "confidence": r.confidence,
                    "direction": r.direction,
                    "expected_max_confidence": r.expected_max_confidence,
                    "flagged": r.flagged,
                    "crashed": r.crashed,
                    "thesis": r.thesis_text,
                }
                for r in results
            ],
            indent=2,
        )
    )
    return out


if __name__ == "__main__":
    results = run_adversarial()
    _print_results(results)
    saved = save_results(results)
    print(f"Results saved to {saved}")
    flagged_count = sum(1 for r in results if r.flagged)
    crash_count = sum(1 for r in results if r.crashed)
    if flagged_count:
        print(f"\nWARNING: {flagged_count} case(s) flagged for overconfidence.")
    if crash_count:
        print(f"WARNING: {crash_count} case(s) crashed on adversarial input.")
