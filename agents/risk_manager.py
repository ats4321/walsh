"""Risk Manager: a hard-rules gate the orchestrator MUST clear before trading.

Unlike the specialist agents, the Risk Manager does not emit an ``AgentThesis``
opinion. It evaluates a *proposed trade* against deterministic risk limits and
returns an approve/veto ``RiskDecision`` with per-rule reasoning. The
orchestrator is required to check ``RiskDecision.approved`` before executing any
trade:

    decision = RiskManager(correlations=...).evaluate(trade, portfolio)
    if not decision.approved:
        log.warning("trade vetoed: %s", decision.veto_reasons)
        return                      # MUST NOT execute
    broker.execute(trade)

Three hard rules (see ``RiskLimits`` for the tunable thresholds):

1. Position size vs. portfolio  -- the *resulting* exposure to one name (current
   holding +/- this trade) can't exceed ``max_position_pct``.
2. Correlation to existing holdings -- the cluster of names correlated to the
   proposed ticker can't exceed ``max_correlated_exposure_pct``.
3. Max drawdown limit -- no exposure-*increasing* trades while the portfolio is
   at or beyond ``max_drawdown_limit`` below its peak. Risk-reducing (sell)
   trades stay allowed so the book can be de-risked.
"""

from __future__ import annotations

from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _norm(ticker: str) -> str:
    return ticker.strip().upper()


class ProposedTrade(BaseModel):
    """A trade the orchestrator wants to execute, pending risk approval."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    # "buy" increases exposure, "sell" reduces it. This drives the drawdown rule.
    # ponytail: long-only model -- a short-open is a "buy" of exposure. Add a
    # position_effect field if real shorting arrives.
    side: Literal["buy", "sell"] = "buy"
    notional: float = Field(gt=0, description="Dollar size of the proposed trade.")

    @property
    def increases_exposure(self) -> bool:
        return self.side == "buy"

    @field_validator("ticker")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return _norm(value)


class Holding(BaseModel):
    """An existing portfolio position at current market value."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    market_value: float = Field(gt=0)

    @field_validator("ticker")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return _norm(value)


class Portfolio(BaseModel):
    """Portfolio state the gate evaluates against."""

    model_config = ConfigDict(extra="forbid")

    total_value: float = Field(gt=0, description="Net liquidation value (cash + holdings).")
    holdings: list[Holding] = Field(default_factory=list)
    current_drawdown: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Fraction below the portfolio's peak value (0.0 = at peak).",
    )

    def exposure_to(self, ticker: str) -> float:
        ticker = _norm(ticker)
        return sum(h.market_value for h in self.holdings if h.ticker == ticker)


class RiskLimits(BaseModel):
    """Tunable hard limits. Defaults are conservative starting points."""

    model_config = ConfigDict(extra="forbid")

    max_position_pct: float = Field(default=0.10, gt=0.0, le=1.0)
    corr_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    max_correlated_exposure_pct: float = Field(default=0.25, gt=0.0, le=1.0)
    max_drawdown_limit: float = Field(default=0.20, gt=0.0, le=1.0)


class RiskCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class RiskDecision(BaseModel):
    """Result of the gate. ``approved`` is what the orchestrator MUST check."""

    model_config = ConfigDict(extra="forbid")

    approved: bool
    ticker: str
    checks: list[RiskCheck]
    reasoning: str

    @property
    def veto_reasons(self) -> list[str]:
        return [c.detail for c in self.checks if not c.passed]


class RiskManager:
    """Deterministic approve/veto gate for proposed trades.

    Correlations are supplied by the caller as a symmetric ``{(a, b): rho}``
    mapping (order-insensitive); any unlisted pair is treated as uncorrelated,
    and a ticker is always perfectly correlated with itself (so adding to an
    existing position counts fully against the correlated-exposure limit).
    """

    def __init__(
        self,
        limits: RiskLimits | None = None,
        correlations: Mapping[tuple[str, str], float] | None = None,
    ) -> None:
        self.limits = limits or RiskLimits()
        self._corr: dict[frozenset[str], float] = {
            frozenset((_norm(a), _norm(b))): rho
            for (a, b), rho in (correlations or {}).items()
        }

    def correlation(self, a: str, b: str) -> float:
        a, b = _norm(a), _norm(b)
        if a == b:
            return 1.0
        return self._corr.get(frozenset((a, b)), 0.0)

    def evaluate(self, trade: ProposedTrade, portfolio: Portfolio) -> RiskDecision:
        limits = self.limits
        checks: list[RiskCheck] = []

        # Resulting exposure to this name after the trade nets against any
        # current holding (a sell reduces it; never below zero).
        current = portfolio.exposure_to(trade.ticker)
        delta = trade.notional if trade.increases_exposure else -trade.notional
        resulting = max(0.0, current + delta)

        # Rule 1: position size vs. portfolio.
        pos_pct = resulting / portfolio.total_value
        checks.append(RiskCheck(
            name="position_size",
            passed=pos_pct <= limits.max_position_pct,
            detail=(
                f"{trade.ticker} would be {pos_pct:.1%} of portfolio "
                f"(limit {limits.max_position_pct:.1%})"
            ),
        ))

        # Rule 2: correlation to existing holdings (concentration in a cluster).
        correlated = [
            h for h in portfolio.holdings
            if h.ticker != trade.ticker
            and self.correlation(trade.ticker, h.ticker) >= limits.corr_threshold
        ]
        cluster_notional = resulting + sum(h.market_value for h in correlated)
        cluster_pct = cluster_notional / portfolio.total_value
        names = ", ".join(h.ticker for h in correlated) or "none"
        checks.append(RiskCheck(
            name="correlated_exposure",
            passed=cluster_pct <= limits.max_correlated_exposure_pct,
            detail=(
                f"Correlated cluster {cluster_pct:.1%} of portfolio "
                f"(limit {limits.max_correlated_exposure_pct:.1%}; "
                f"correlated holdings: {names})"
            ),
        ))

        # Rule 3: max drawdown -- block exposure-increasing trades once breached;
        # allow risk-reducing (sell) trades so the book can be de-risked.
        breached = (
            portfolio.current_drawdown >= limits.max_drawdown_limit
            and trade.increases_exposure
        )
        checks.append(RiskCheck(
            name="max_drawdown",
            passed=not breached,
            detail=(
                f"Portfolio drawdown {portfolio.current_drawdown:.1%} "
                f"(limit {limits.max_drawdown_limit:.1%}); "
                f"{'blocks new exposure' if breached else 'ok'}"
            ),
        ))

        approved = all(c.passed for c in checks)
        if approved:
            reasoning = f"APPROVED {trade.ticker}: within all risk limits."
        else:
            reasons = "; ".join(c.detail for c in checks if not c.passed)
            reasoning = f"VETOED {trade.ticker}: {reasons}."

        return RiskDecision(
            approved=approved,
            ticker=trade.ticker,
            checks=checks,
            reasoning=reasoning,
        )


def _demo() -> None:
    """Runnable self-check: `python agents/risk_manager.py`."""

    portfolio = Portfolio(
        total_value=1_000_000,
        holdings=[
            Holding(ticker="AAPL", market_value=80_000),
            Holding(ticker="MSFT", market_value=80_000),
        ],
        current_drawdown=0.05,
    )
    # AAPL/MSFT and the new NVDA are all highly correlated mega-cap tech.
    rm = RiskManager(correlations={
        ("NVDA", "AAPL"): 0.8,
        ("NVDA", "MSFT"): 0.75,
    })

    # Clean approve: small, uncorrelated name, healthy portfolio.
    ok = rm.evaluate(ProposedTrade(ticker="XOM", notional=50_000), portfolio)
    assert ok.approved, ok.reasoning

    # Rule 1: single position too large (15% > 10%).
    big = rm.evaluate(ProposedTrade(ticker="XOM", notional=150_000), portfolio)
    assert not big.approved and any(
        c.name == "position_size" and not c.passed for c in big.checks
    ), big.reasoning

    # Rule 1 (netting): adding 30k to the existing 80k AAPL -> 110k = 11% > 10%.
    add = rm.evaluate(ProposedTrade(ticker="AAPL", notional=30_000), portfolio)
    assert not add.approved and any(
        c.name == "position_size" and not c.passed for c in add.checks
    ), add.reasoning

    # Rule 2: correlated cluster too large (NVDA 95k + AAPL 80k + MSFT 80k = 25.5%).
    corr = rm.evaluate(ProposedTrade(ticker="NVDA", notional=95_000), portfolio)
    assert not corr.approved and any(
        c.name == "correlated_exposure" and not c.passed for c in corr.checks
    ), corr.reasoning
    # Position size alone is fine (9.5% < 10%): the cluster rule is what vetoes.
    assert next(c for c in corr.checks if c.name == "position_size").passed

    # Rule 3: drawdown breached -> block a buy, but still allow a de-risking sell.
    drawn = Portfolio(
        total_value=1_000_000,
        holdings=[Holding(ticker="AAPL", market_value=50_000)],
        current_drawdown=0.25,
    )
    buy = rm.evaluate(ProposedTrade(ticker="XOM", side="buy", notional=10_000), drawn)
    assert not buy.approved and any(
        c.name == "max_drawdown" and not c.passed for c in buy.checks
    ), buy.reasoning
    sell = rm.evaluate(ProposedTrade(ticker="AAPL", side="sell", notional=10_000), drawn)
    assert sell.approved, sell.reasoning

    # Same-ticker add is fully correlated with itself.
    assert rm.correlation("AAPL", "aapl") == 1.0

    print("risk_manager self-check passed")
    print(" approve:", ok.reasoning)
    print(" veto:   ", corr.reasoning)


if __name__ == "__main__":
    _demo()
