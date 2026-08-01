"""
Orchestrator: runs Fundamental, Technical, Sentiment, Macro agents in parallel,
passes their AgentThesis outputs to Portfolio Manager, then gates through
Risk Manager before returning the final decision.

All events are logged to the in-process memory store (and optionally to a
JSON-lines file for persistence).
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Optional

import httpx

from .agents import (
    FetchFn,
    fundamental_agent,
    macro_agent,
    portfolio_manager,
    risk_manager,
    sentiment_agent,
    technical_agent,
)
from .models import AgentThesis, FinalDecision

logger = logging.getLogger(__name__)

# ── Memory store ──────────────────────────────────────────────────────────────

_memory: list[dict] = []


def log_event(event_type: str, **data) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **data,
    }
    _memory.append(entry)
    logger.info("[%s] %s", event_type, data)


def get_memory() -> list[dict]:
    return list(_memory)


def flush_memory_to_file(path: Path) -> None:
    with path.open("a") as fh:
        for entry in _memory:
            fh.write(json.dumps(entry) + "\n")


def clear_memory() -> None:
    _memory.clear()


# ── Default HTTP fetch ────────────────────────────────────────────────────────

async def _http_fetch(url: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def run_pipeline(
    ticker: str,
    fetch_fn: Optional[FetchFn] = None,
) -> FinalDecision:
    """
    Full analysis pipeline for one ticker.

    Args:
        ticker:   Stock ticker symbol (e.g. "AAPL").
        fetch_fn: Async callable (url -> dict). Defaults to real HTTP. Pass a
                  mock for testing.

    Returns:
        FinalDecision after Risk Manager gate.
    """
    _fetch = fetch_fn or _http_fetch
    ticker = ticker.upper()

    log_event("pipeline_start", ticker=ticker)

    # 1. Run analysis agents in parallel
    theses: tuple[AgentThesis, ...] = await asyncio.gather(
        fundamental_agent(ticker, _fetch),
        technical_agent(ticker, _fetch),
        sentiment_agent(ticker, _fetch),
        macro_agent(ticker, _fetch),
    )

    for thesis in theses:
        log_event(
            "agent_thesis",
            agent=thesis.agent,
            ticker=thesis.ticker,
            signal=thesis.signal.value,
            confidence=thesis.confidence,
            reasoning=thesis.reasoning,
        )

    # 2. Portfolio Manager synthesizes
    pm_decision = portfolio_manager(ticker, list(theses))
    log_event(
        "portfolio_decision",
        ticker=pm_decision.ticker,
        signal=pm_decision.signal.value,
        confidence=pm_decision.confidence,
        reasoning=pm_decision.reasoning,
    )

    # 3. Risk Manager gates
    final = risk_manager(pm_decision)
    log_event(
        "final_decision",
        ticker=final.ticker,
        signal=final.signal.value,
        confidence=final.confidence,
        approved=final.approved,
        risk_notes=final.risk_notes,
    )

    log_event("pipeline_complete", ticker=ticker, approved=final.approved)
    return final


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    result = asyncio.run(run_pipeline(ticker))
    print(json.dumps(
        {
            "ticker": result.ticker,
            "signal": result.signal.value,
            "confidence": result.confidence,
            "approved": result.approved,
            "risk_notes": result.risk_notes,
            "reasoning": result.reasoning,
        },
        indent=2,
    ))
