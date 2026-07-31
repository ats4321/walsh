"""Trading-desk orchestrator.

Runs four analysis agents (Fundamental, Technical, Sentiment, Macro) in
parallel, hands their theses to a Portfolio Manager that proposes a call,
then runs a Risk Manager as a gate before returning the final decision.
Every step is logged to a memory store.

Run:  python -m orchestrator.main AAPL
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass, field, asdict


# --------------------------------------------------------------------------- #
# Data access seam.
#
# ponytail: these return deterministic placeholder feeds so the pipeline runs
# out of the box. In production swap the bodies for real market-data API calls
# (keep the signatures) — the integration test mocks them at this seam.
# --------------------------------------------------------------------------- #

def _seed(ticker: str) -> int:
    return sum(ord(c) for c in ticker.upper())


async def fetch_fundamentals(ticker: str) -> dict:
    s = _seed(ticker)
    return {"pe_ratio": 10 + s % 35, "revenue_growth": ((s % 40) - 15) / 100}


async def fetch_prices(ticker: str) -> dict:
    s = _seed(ticker)
    return {"momentum": ((s % 20) - 10) / 10, "rsi": 30 + s % 50}


async def fetch_news(ticker: str) -> dict:
    s = _seed(ticker)
    return {"sentiment_score": ((s % 20) - 10) / 10}


async def fetch_macro(ticker: str) -> dict:
    regimes = ["expansion", "neutral", "recession"]
    return {"regime": regimes[_seed(ticker) % 3]}


# --------------------------------------------------------------------------- #
# Domain types
# --------------------------------------------------------------------------- #

BUY, HOLD, SELL = "BUY", "HOLD", "SELL"
_SCORE = {BUY: 1, HOLD: 0, SELL: -1}


@dataclass
class AgentThesis:
    agent: str
    ticker: str
    signal: str            # BUY | HOLD | SELL
    confidence: float      # 0.0 .. 1.0
    rationale: str
    data: dict = field(default_factory=dict)


@dataclass
class FinalDecision:
    ticker: str
    action: str            # BUY | HOLD | SELL (after risk gate)
    confidence: float
    approved: bool         # did the risk gate approve the PM's proposal?
    proposed_action: str   # what the PM wanted before the gate
    rationale: str
    theses: list = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Memory store
# --------------------------------------------------------------------------- #

class MemoryStore:
    """Append-only log of everything the pipeline does."""

    def __init__(self):
        self.entries: list[dict] = []

    def log(self, kind: str, ticker: str, payload) -> None:
        if hasattr(payload, "__dataclass_fields__"):
            payload = asdict(payload)
        self.entries.append(
            {"ts": time.time(), "kind": kind, "ticker": ticker, "payload": payload}
        )

    def by_ticker(self, ticker: str) -> list[dict]:
        return [e for e in self.entries if e["ticker"] == ticker]


# --------------------------------------------------------------------------- #
# Analysis agents
# --------------------------------------------------------------------------- #

class Agent:
    name = "agent"
    fetch_name = None  # module-level fetcher, resolved at call time so tests can mock it

    async def run(self, ticker: str, memory: MemoryStore) -> AgentThesis:
        data = await globals()[self.fetch_name](ticker)
        thesis = self.analyze(ticker, data)
        memory.log("thesis", ticker, thesis)
        return thesis

    def analyze(self, ticker: str, data: dict) -> AgentThesis:  # pragma: no cover
        raise NotImplementedError


def _thesis(agent, ticker, signal, confidence, rationale, data) -> AgentThesis:
    return AgentThesis(agent, ticker, signal, max(0.0, min(1.0, confidence)),
                       rationale, data)


class FundamentalAgent(Agent):
    name = "Fundamental"
    fetch_name = "fetch_fundamentals"

    def analyze(self, ticker, data):
        g, pe = data["revenue_growth"], data["pe_ratio"]
        if g > 0.10 and pe < 25:
            sig, conf = BUY, 0.5 + g
        elif g < 0 or pe > 40:
            sig, conf = SELL, 0.5 + abs(g)
        else:
            sig, conf = HOLD, 0.4
        return _thesis(self.name, ticker, sig, conf,
                       f"growth={g:.0%}, P/E={pe}", data)


class TechnicalAgent(Agent):
    name = "Technical"
    fetch_name = "fetch_prices"

    def analyze(self, ticker, data):
        mom, rsi = data["momentum"], data["rsi"]
        if mom > 0 and rsi < 70:
            sig, conf = BUY, 0.5 + mom / 2
        elif mom < 0 or rsi >= 70:
            sig, conf = SELL, 0.5 + abs(mom) / 2
        else:
            sig, conf = HOLD, 0.4
        return _thesis(self.name, ticker, sig, conf,
                       f"momentum={mom:.2f}, RSI={rsi}", data)


class SentimentAgent(Agent):
    name = "Sentiment"
    fetch_name = "fetch_news"

    def analyze(self, ticker, data):
        s = data["sentiment_score"]
        if s > 0.3:
            sig, conf = BUY, s
        elif s < -0.3:
            sig, conf = SELL, abs(s)
        else:
            sig, conf = HOLD, 0.4
        return _thesis(self.name, ticker, sig, conf, f"sentiment={s:.2f}", data)


class MacroAgent(Agent):
    name = "Macro"
    fetch_name = "fetch_macro"

    def analyze(self, ticker, data):
        regime = data["regime"]
        sig = {"expansion": BUY, "recession": SELL}.get(regime, HOLD)
        conf = 0.6 if sig != HOLD else 0.4
        return _thesis(self.name, ticker, sig, conf, f"regime={regime}", data)


ANALYSTS = [FundamentalAgent, TechnicalAgent, SentimentAgent, MacroAgent]


# --------------------------------------------------------------------------- #
# Portfolio Manager + Risk Manager
# --------------------------------------------------------------------------- #

class PortfolioManager:
    """Synthesizes the analyst theses into a single proposed call."""

    BUY_THRESHOLD = 0.15   # confidence-weighted score needed to act

    def synthesize(self, ticker: str, theses: list[AgentThesis]) -> AgentThesis:
        weight = sum(t.confidence for t in theses) or 1.0
        score = sum(_SCORE[t.signal] * t.confidence for t in theses) / weight
        if score > self.BUY_THRESHOLD:
            action = BUY
        elif score < -self.BUY_THRESHOLD:
            action = SELL
        else:
            action = HOLD
        agrees = [t for t in theses if t.signal == action]
        conf = sum(t.confidence for t in agrees) / len(agrees) if agrees else 0.4
        rationale = "; ".join(f"{t.agent}:{t.signal}({t.confidence:.2f})"
                              for t in theses)
        return _thesis("PortfolioManager", ticker, action, conf,
                       f"score={score:+.2f} -> {action} | {rationale}",
                       {"score": score})


class RiskManager:
    """Gate: can approve, downgrade, or veto the PM's proposed call."""

    MIN_CONFIDENCE = 0.35   # don't act on weak conviction
    MACRO_VETO = SELL       # macro headwind vetoes a BUY

    def review(self, ticker, proposal: AgentThesis,
               theses: list[AgentThesis]) -> FinalDecision:
        macro = next((t for t in theses if t.agent == "Macro"), None)
        reasons = []
        action, approved = proposal.signal, True

        if proposal.signal != HOLD and proposal.confidence < self.MIN_CONFIDENCE:
            action, approved = HOLD, False
            reasons.append(f"confidence {proposal.confidence:.2f} < "
                           f"{self.MIN_CONFIDENCE} floor")

        if (proposal.signal == BUY and macro and macro.signal == self.MACRO_VETO
                and macro.confidence >= 0.5):
            action, approved = HOLD, False
            reasons.append("macro headwind vetoes BUY")

        rationale = ("approved: " + proposal.rationale) if approved \
            else "; ".join(reasons)
        return FinalDecision(
            ticker=ticker,
            action=action,
            confidence=proposal.confidence,
            approved=approved,
            proposed_action=proposal.signal,
            rationale=rationale,
            theses=theses,
        )


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

async def orchestrate(ticker: str, memory: MemoryStore | None = None) -> FinalDecision:
    memory = memory or MemoryStore()
    ticker = ticker.upper()
    memory.log("start", ticker, {"agents": [a.name for a in ANALYSTS]})

    theses = await asyncio.gather(
        *(cls().run(ticker, memory) for cls in ANALYSTS)
    )

    proposal = PortfolioManager().synthesize(ticker, list(theses))
    memory.log("proposal", ticker, proposal)

    decision = RiskManager().review(ticker, proposal, list(theses))
    memory.log("decision", ticker, decision)
    return decision


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    ticker = argv[0] if argv else "AAPL"
    memory = MemoryStore()
    decision = asyncio.run(orchestrate(ticker, memory))
    print(f"{decision.ticker}: {decision.action} "
          f"(proposed {decision.proposed_action}, "
          f"approved={decision.approved}, conf={decision.confidence:.2f})")
    print(f"  {decision.rationale}")
    print(f"  logged {len(memory.entries)} memory entries")
    return decision


if __name__ == "__main__":
    main()
