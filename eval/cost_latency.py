"""Cost and latency tracking for Walsh pipeline runs.

Tracks per-agent token usage and wall-clock time, then reports total API
cost using Anthropic's published pricing.

Usage:
    from eval.cost_latency import PipelineTracker

    tracker = PipelineTracker()
    with tracker.track_agent("TechnicalSignalAgent"):
        thesis = agent.analyze()
        tracker.record_tokens("TechnicalSignalAgent", input_tokens=512, output_tokens=128)

    report = tracker.report()
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

RESULTS_DIR = Path(__file__).parent / "results"

# Anthropic pricing per million tokens (as of mid-2025; update if changed)
# https://www.anthropic.com/api
MODEL_PRICING: dict[str, dict[str, float]] = {
    # claude-3-5-sonnet / claude-sonnet-4-6
    "claude-3-5-sonnet-latest": {"input_per_mtok": 3.0, "output_per_mtok": 15.0},
    "claude-sonnet-4-6": {"input_per_mtok": 3.0, "output_per_mtok": 15.0},
    # claude-3-haiku / claude-haiku-4-5
    "claude-3-haiku-20240307": {"input_per_mtok": 0.25, "output_per_mtok": 1.25},
    "claude-haiku-4-5-20251001": {"input_per_mtok": 0.8, "output_per_mtok": 4.0},
    # claude-3-opus / claude-opus-4-8
    "claude-3-opus-20240229": {"input_per_mtok": 15.0, "output_per_mtok": 75.0},
    "claude-opus-4-8": {"input_per_mtok": 15.0, "output_per_mtok": 75.0},
}
DEFAULT_MODEL = "claude-3-5-sonnet-latest"


def cost_usd(
    input_tokens: int,
    output_tokens: int,
    model: str = DEFAULT_MODEL,
) -> float:
    """Compute API cost in USD for a single call."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING[DEFAULT_MODEL])
    return (
        input_tokens / 1_000_000 * pricing["input_per_mtok"]
        + output_tokens / 1_000_000 * pricing["output_per_mtok"]
    )


# ---------------------------------------------------------------------------
# Per-agent record
# ---------------------------------------------------------------------------

@dataclass
class AgentRecord:
    agent_name: str
    model: str = DEFAULT_MODEL
    input_tokens: int = 0
    output_tokens: int = 0
    wall_time_s: float = 0.0

    @property
    def cost_usd(self) -> float:
        return cost_usd(self.input_tokens, self.output_tokens, self.model)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "wall_time_s": round(self.wall_time_s, 4),
            "cost_usd": round(self.cost_usd, 8),
        }


# ---------------------------------------------------------------------------
# Pipeline tracker
# ---------------------------------------------------------------------------

class PipelineTracker:
    """
    Collect cost and latency data across one full pipeline run.

    Usage:
        tracker = PipelineTracker()
        with tracker.track_agent("TechnicalSignalAgent") as ctx:
            response = agent.analyze()
            ctx.record_tokens(in_tokens, out_tokens)
        report = tracker.report()
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.default_model = model
        self._records: list[AgentRecord] = []
        self._run_start: float = time.monotonic()

    @contextmanager
    def track_agent(
        self, agent_name: str, model: str | None = None
    ) -> Generator[_AgentContext, None, None]:
        record = AgentRecord(agent_name=agent_name, model=model or self.default_model)
        t0 = time.monotonic()
        ctx = _AgentContext(record)
        try:
            yield ctx
        finally:
            record.wall_time_s = time.monotonic() - t0
            self._records.append(record)

    def record_tokens(
        self,
        agent_name: str,
        input_tokens: int,
        output_tokens: int,
        model: str | None = None,
    ) -> None:
        """Convenience method to record tokens outside a context manager."""
        record = AgentRecord(
            agent_name=agent_name,
            model=model or self.default_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        self._records.append(record)

    def ingest_anthropic_response(
        self, agent_name: str, response: Any, model: str | None = None
    ) -> None:
        """Extract usage from an Anthropic SDK response object."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self.record_tokens(
            agent_name,
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            model=model,
        )

    def report(self) -> dict[str, Any]:
        total_input = sum(r.input_tokens for r in self._records)
        total_output = sum(r.output_tokens for r in self._records)
        total_cost = sum(r.cost_usd for r in self._records)
        total_wall = time.monotonic() - self._run_start

        return {
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "totals": {
                "input_tokens": total_input,
                "output_tokens": total_output,
                "total_tokens": total_input + total_output,
                "cost_usd": round(total_cost, 6),
                "wall_time_s": round(total_wall, 4),
            },
            "per_agent": [r.to_dict() for r in self._records],
        }

    def save(self, path: Path | None = None) -> Path:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = path or RESULTS_DIR / f"{ts}_cost_latency.json"
        out.write_text(json.dumps(self.report(), indent=2))
        return out

    def print_summary(self) -> None:
        report = self.report()
        totals = report["totals"]
        print(f"\n=== Pipeline Cost & Latency ===")
        print(f"  Total tokens: {totals['total_tokens']:,} ({totals['input_tokens']:,} in / {totals['output_tokens']:,} out)")
        print(f"  Estimated cost: ${totals['cost_usd']:.6f}")
        print(f"  Wall time: {totals['wall_time_s']:.2f}s")
        print("\n  Per agent:")
        for rec in report["per_agent"]:
            print(
                f"    {rec['agent_name']}: "
                f"{rec['wall_time_s']:.3f}s, "
                f"{rec['input_tokens']+rec['output_tokens']:,} tokens, "
                f"${rec['cost_usd']:.6f}"
            )


class _AgentContext:
    """Yielded inside track_agent() so callers can add token counts mid-flight."""

    def __init__(self, record: AgentRecord) -> None:
        self._record = record

    def record_tokens(self, input_tokens: int, output_tokens: int) -> None:
        self._record.input_tokens += input_tokens
        self._record.output_tokens += output_tokens
