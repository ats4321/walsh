"""
Analysis agents: Fundamental, Technical, Sentiment, Macro.
Synthesis agents: Portfolio Manager, Risk Manager.

Each agent accepts a ticker and a fetch_fn coroutine with signature:
    async def fetch_fn(url: str) -> dict
so the HTTP layer is injectable for testing.
"""

from typing import Awaitable, Callable

from .models import (
    AgentThesis,
    FinalDecision,
    PortfolioDecision,
    Signal,
    score_to_signal,
    signal_to_score,
)

FetchFn = Callable[[str], Awaitable[dict]]

_BASE = "https://api.finance.example.com"


async def fundamental_agent(ticker: str, fetch_fn: FetchFn) -> AgentThesis:
    data = await fetch_fn(f"{_BASE}/fundamental/{ticker}")

    pe = data.get("pe_ratio", 20)
    growth = data.get("revenue_growth", 0.05)
    margin = data.get("profit_margin", 0.1)
    debt = data.get("debt_to_equity", 1.0)

    score = 0
    if pe < 15:
        score += 1
    elif pe > 30:
        score -= 1

    if growth > 0.15:
        score += 1
    elif growth < 0:
        score -= 1

    if margin > 0.2:
        score += 1
    elif margin < 0.05:
        score -= 1

    if debt > 2:
        score -= 1

    signal = score_to_signal(score)
    confidence = min(0.9, 0.5 + abs(score) * 0.15)

    return AgentThesis(
        agent="fundamental",
        ticker=ticker,
        signal=signal,
        confidence=confidence,
        reasoning=(
            f"PE={pe}, revenue_growth={growth:.0%}, "
            f"profit_margin={margin:.0%}, D/E={debt:.1f} → score={score}"
        ),
        metadata=data,
    )


async def technical_agent(ticker: str, fetch_fn: FetchFn) -> AgentThesis:
    data = await fetch_fn(f"{_BASE}/technical/{ticker}")

    rsi = data.get("rsi", 50)
    macd = data.get("macd_histogram", 0)
    golden_cross = data.get("golden_cross", False)

    score = 0
    if rsi < 30:
        score += 2
    elif rsi < 50:
        score += 1
    elif rsi > 70:
        score -= 1

    if macd > 0:
        score += 1
    elif macd < 0:
        score -= 1

    if golden_cross:
        score += 1

    signal = score_to_signal(score)
    confidence = min(0.9, 0.4 + abs(score) * 0.1)

    return AgentThesis(
        agent="technical",
        ticker=ticker,
        signal=signal,
        confidence=confidence,
        reasoning=f"RSI={rsi}, MACD_hist={macd:.3f}, golden_cross={golden_cross} → score={score}",
        metadata=data,
    )


async def sentiment_agent(ticker: str, fetch_fn: FetchFn) -> AgentThesis:
    data = await fetch_fn(f"{_BASE}/sentiment/{ticker}")

    news_score = data.get("news_score", 0.0)   # -1.0 to 1.0
    social_score = data.get("social_score", 0.0)
    insider_activity = data.get("insider_buying", False)

    combined = (news_score + social_score) / 2
    score = round(combined * 2)  # map [-1,1] → [-2,2]
    if insider_activity:
        score = min(2, score + 1)

    signal = score_to_signal(score)
    confidence = min(0.85, 0.4 + abs(combined) * 0.4)

    return AgentThesis(
        agent="sentiment",
        ticker=ticker,
        signal=signal,
        confidence=confidence,
        reasoning=(
            f"news={news_score:.2f}, social={social_score:.2f}, "
            f"insider_buying={insider_activity} → score={score}"
        ),
        metadata=data,
    )


async def macro_agent(ticker: str, fetch_fn: FetchFn) -> AgentThesis:
    data = await fetch_fn(f"{_BASE}/macro")

    gdp_growth = data.get("gdp_growth", 0.02)
    fed_rate = data.get("fed_rate", 0.05)
    inflation = data.get("inflation", 0.03)
    sector = data.get("sector_outlook", "neutral")

    score = 0
    if gdp_growth > 0.025:
        score += 1
    elif gdp_growth < 0:
        score -= 1

    if fed_rate < 0.04:
        score += 1
    elif fed_rate > 0.06:
        score -= 1

    if inflation < 0.03:
        score += 1
    elif inflation > 0.05:
        score -= 1

    if sector == "bullish":
        score += 1
    elif sector == "bearish":
        score -= 1

    signal = score_to_signal(score)
    confidence = min(0.8, 0.4 + abs(score) * 0.1)

    return AgentThesis(
        agent="macro",
        ticker=ticker,
        signal=signal,
        confidence=confidence,
        reasoning=(
            f"GDP={gdp_growth:.1%}, fed_rate={fed_rate:.1%}, "
            f"inflation={inflation:.1%}, sector={sector} → score={score}"
        ),
        metadata=data,
    )


def portfolio_manager(
    ticker: str, theses: list[AgentThesis]
) -> PortfolioDecision:
    """Synthesize agent theses via confidence-weighted signal average."""
    total_weight = sum(t.confidence for t in theses)
    weighted_score = sum(
        signal_to_score(t.signal) * t.confidence for t in theses
    ) / total_weight

    signal = score_to_signal(weighted_score)
    # consensus confidence: penalised by disagreement spread
    scores = [signal_to_score(t.signal) for t in theses]
    spread = max(scores) - min(scores)
    avg_conf = total_weight / len(theses)
    confidence = round(avg_conf * max(0.5, 1 - spread * 0.1), 4)

    breakdown = ", ".join(
        f"{t.agent}={t.signal.value}({t.confidence:.0%})" for t in theses
    )
    reasoning = (
        f"Weighted score={weighted_score:.2f} → {signal.value}. "
        f"Agents: [{breakdown}]"
    )

    return PortfolioDecision(
        ticker=ticker,
        signal=signal,
        confidence=confidence,
        reasoning=reasoning,
        component_theses=theses,
    )


def risk_manager(decision: PortfolioDecision) -> FinalDecision:
    """Gate the portfolio decision; reject if confidence too low or signals wildly mixed."""
    scores = [signal_to_score(t.signal) for t in decision.component_theses]
    spread = max(scores) - min(scores)

    risk_notes: list[str] = []
    approved = True

    if decision.confidence < 0.45:
        approved = False
        risk_notes.append(
            f"Confidence {decision.confidence:.0%} below 45% threshold"
        )

    if spread >= 4:  # max possible spread is 4 (STRONG_BUY vs STRONG_SELL)
        approved = False
        risk_notes.append(f"Agent signal spread={spread} — extreme disagreement")

    # Downgrade STRONG signals to one tier when confidence is marginal
    signal = decision.signal
    if approved and decision.confidence < 0.65:
        if signal == Signal.STRONG_BUY:
            signal = Signal.BUY
            risk_notes.append("Downgraded STRONG_BUY → BUY (marginal confidence)")
        elif signal == Signal.STRONG_SELL:
            signal = Signal.SELL
            risk_notes.append("Downgraded STRONG_SELL → SELL (marginal confidence)")

    if not risk_notes:
        risk_notes.append("No risk flags")

    return FinalDecision(
        ticker=decision.ticker,
        signal=signal if approved else Signal.HOLD,
        confidence=decision.confidence,
        reasoning=decision.reasoning,
        approved=approved,
        risk_notes="; ".join(risk_notes),
        component_theses=decision.component_theses,
    )
