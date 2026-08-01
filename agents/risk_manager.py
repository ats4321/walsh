"""Risk Manager: the hard gate the orchestrator MUST clear before any trade.

Unlike the opinion-producing agents, this one does not advise — it decides.
It checks a proposed trade against hard, non-negotiable limits and returns an
approve/veto verdict with a reason per rule. Any veto = do not execute.

Usage (orchestrator side):

    decision = evaluate(trade, portfolio, correlations, limits)
    if not decision.approved:
        log.warning("trade vetoed: %s", decision.veto_reasons)
        return                      # MUST NOT execute
    broker.execute(trade)

ponytail: data shapes below are the minimal fields the rules need. If real
Trade/Portfolio types already exist elsewhere, swap these dataclasses for them —
the rule logic is unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Trade:
    symbol: str
    side: str          # "buy" (increases exposure) or "sell" (decreases)
    quantity: float
    price: float

    @property
    def notional(self) -> float:
        return abs(self.quantity) * self.price

    @property
    def increases_exposure(self) -> bool:
        # ponytail: models long-only. A "sell" opening a short increases
        # exposure too — pass side="buy" for short-opens, or add a
        # `position_effect` field when shorting matters.
        return self.side == "buy"


@dataclass(frozen=True)
class Portfolio:
    equity: float                              # total account value
    positions: dict[str, float]                # symbol -> current market value
    high_water_mark: float                     # peak equity ever reached

    @property
    def drawdown(self) -> float:
        if self.high_water_mark <= 0:
            return 0.0
        return max(0.0, (self.high_water_mark - self.equity) / self.high_water_mark)


@dataclass(frozen=True)
class RiskLimits:
    max_position_pct: float = 0.10      # one symbol's exposure / equity
    max_correlated_pct: float = 0.30    # summed exposure of correlated cluster / equity
    correlation_threshold: float = 0.7  # |corr| at/above which two symbols cluster
    max_drawdown: float = 0.20          # block new exposure once breached


@dataclass
class RiskDecision:
    approved: bool
    reasons: list[str] = field(default_factory=list)        # every rule's verdict
    veto_reasons: list[str] = field(default_factory=list)   # only the failing ones


def _corr(correlations: dict, a: str, b: str) -> float:
    if a == b:
        return 1.0
    # symmetric lookup; missing pair assumed uncorrelated
    return correlations.get((a, b), correlations.get((b, a), 0.0))


def evaluate(
    trade: Trade,
    portfolio: Portfolio,
    correlations: dict[tuple[str, str], float] | None = None,
    limits: RiskLimits = RiskLimits(),
) -> RiskDecision:
    """Return an approve/veto decision for `trade`. Any failed rule vetoes."""
    correlations = correlations or {}
    equity = portfolio.equity
    reasons: list[str] = []
    vetoes: list[str] = []

    if equity <= 0:
        return RiskDecision(False, ["equity <= 0; no trading"], ["equity <= 0; no trading"])

    def check(ok: bool, msg: str) -> None:
        reasons.append(("PASS " if ok else "VETO ") + msg)
        if not ok:
            vetoes.append(msg)

    # Post-trade exposure for this symbol (long-only model).
    current = portfolio.positions.get(trade.symbol, 0.0)
    resulting = current + trade.notional if trade.increases_exposure else current - trade.notional
    resulting = max(0.0, resulting)

    # Rule 1: single-position size vs portfolio.
    pos_pct = resulting / equity
    check(
        pos_pct <= limits.max_position_pct,
        f"position {trade.symbol} would be {pos_pct:.1%} of equity "
        f"(limit {limits.max_position_pct:.0%})",
    )

    # Rule 2: correlated-cluster concentration. Sum exposure of holdings that
    # correlate with the traded symbol, include the resulting position.
    cluster = resulting
    for sym, value in portfolio.positions.items():
        if sym == trade.symbol:
            continue
        if abs(_corr(correlations, trade.symbol, sym)) >= limits.correlation_threshold:
            cluster += value
    corr_pct = cluster / equity
    check(
        corr_pct <= limits.max_correlated_pct,
        f"correlated cluster around {trade.symbol} would be {corr_pct:.1%} of equity "
        f"(limit {limits.max_correlated_pct:.0%})",
    )

    # Rule 3: drawdown circuit breaker — block exposure-increasing trades once
    # the account is in max drawdown. Risk-reducing trades stay allowed.
    dd = portfolio.drawdown
    breached = dd >= limits.max_drawdown and trade.increases_exposure
    check(
        not breached,
        f"drawdown {dd:.1%} at/over limit {limits.max_drawdown:.0%}; "
        f"no exposure-increasing trades",
    )

    return RiskDecision(approved=not vetoes, reasons=reasons, veto_reasons=vetoes)


if __name__ == "__main__":
    # ponytail: one runnable check per rule + the happy path.
    base = Portfolio(equity=100_000, positions={"AAPL": 5_000}, high_water_mark=100_000)

    ok = evaluate(Trade("MSFT", "buy", 10, 300), base)
    assert ok.approved, ok.veto_reasons

    # Rule 1: 15k on 100k equity > 10% limit.
    big = evaluate(Trade("MSFT", "buy", 50, 300), base)
    assert not big.approved and "of equity" in big.veto_reasons[0]

    # Rule 2: MSFT+AAPL correlated; 5k held + 8k new = 13k... bump limits to
    # isolate: hold 25k AAPL, add 8k MSFT correlated => 33% > 30%.
    corr_pf = Portfolio(equity=100_000, positions={"AAPL": 25_000}, high_water_mark=100_000)
    corr = evaluate(
        Trade("MSFT", "buy", 8_000, 1),
        corr_pf,
        correlations={("MSFT", "AAPL"): 0.85},
    )
    assert not corr.approved and any("correlated cluster" in v for v in corr.veto_reasons), corr

    # Rule 3: 25% drawdown blocks a buy but not a sell.
    dd_pf = Portfolio(equity=75_000, positions={"AAPL": 5_000}, high_water_mark=100_000)
    assert not evaluate(Trade("MSFT", "buy", 1, 100), dd_pf).approved
    assert evaluate(Trade("AAPL", "sell", 1, 100), dd_pf).approved

    print("risk_manager self-check passed")
