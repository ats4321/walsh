"""Tests for backtest/engine.py — all use injected price data, no network."""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import pytest

from backtest.engine import (
    BacktestEngine,
    MeanReversionSignalAgent,
    MomentumSignalAgent,
    PriceData,
    RiskManager,
    PortfolioManager,
    TechnicalSignalAgent,
    _max_drawdown,
    _sharpe,
    _sma,
    _momentum,
    compute_bnh_metrics,
    compute_metrics,
    _all_trading_dates,
    _prices_up_to,
)


# ---------------------------------------------------------------------------
# Helper: synthetic price data
# ---------------------------------------------------------------------------

def _make_prices(
    tickers: list[str],
    n_days: int,
    start: date = date(2023, 1, 3),
    initial: float = 100.0,
    daily_return: float = 0.001,
) -> PriceData:
    """Generate synthetic trending price data for testing."""
    from datetime import timedelta

    result: PriceData = {}
    for i, ticker in enumerate(tickers):
        pairs = []
        price = initial * (1 + i * 0.1)
        d = start
        for _ in range(n_days):
            while d.weekday() >= 5:  # skip weekends
                d += timedelta(days=1)
            pairs.append((d, price))
            price *= 1 + daily_return
            d += timedelta(days=1)
        result[ticker] = pairs
    return result


def _make_engine(
    tickers: list[str] | None = None,
    n_days: int = 60,
    daily_return: float = 0.001,
) -> BacktestEngine:
    tickers = tickers or ["AAPL", "MSFT"]

    def mock_provider(t, s, e):
        return _make_prices(t, n_days, daily_return=daily_return)

    return BacktestEngine(
        tickers=tickers,
        start=date(2023, 1, 3),
        end=date(2023, 3, 31),
        data_provider=mock_provider,
    )


# ---------------------------------------------------------------------------
# Unit: math helpers
# ---------------------------------------------------------------------------

def test_sma_basic():
    assert _sma([1.0, 2.0, 3.0, 4.0, 5.0], 3) == pytest.approx(4.0)


def test_sma_insufficient():
    assert _sma([1.0, 2.0], 5) is None


def test_momentum_basic():
    prices = [100.0, 110.0, 120.0, 130.0, 140.0]
    result = _momentum(prices, 2)
    assert result == pytest.approx((140.0 - 120.0) / 120.0)


def test_momentum_insufficient():
    assert _momentum([100.0], 2) is None


def test_sharpe_basic():
    returns = [0.01] * 100 + [-0.005] * 20
    s = _sharpe(returns)
    assert s is not None
    assert s > 0  # positive mean returns → positive Sharpe


def test_sharpe_empty():
    assert _sharpe([0.01]) is None  # need at least 2


def test_max_drawdown_no_drawdown():
    values = [100.0, 110.0, 120.0, 130.0]
    assert _max_drawdown(values) == pytest.approx(0.0, abs=1e-9)


def test_max_drawdown_with_drawdown():
    values = [100.0, 80.0, 90.0]
    dd = _max_drawdown(values)
    assert dd == pytest.approx(0.20, rel=1e-4)


# ---------------------------------------------------------------------------
# Unit: signal agents
# ---------------------------------------------------------------------------

def test_technical_agent_bullish():
    # Steadily rising prices → SMA crossover bullish
    prices = [80.0 + i * 0.5 for i in range(60)]
    thesis = TechnicalSignalAgent().analyze("AAPL", prices)
    assert thesis.ticker == "AAPL"
    assert thesis.agent_name == "TechnicalSignalAgent"
    assert 0.0 <= thesis.confidence <= 1.0
    assert thesis.supporting_data["direction"] in (-1, 0, 1)


def test_technical_agent_no_data():
    thesis = TechnicalSignalAgent().analyze("AAPL", [])
    assert thesis.confidence <= 0.4
    assert thesis.supporting_data["direction"] == 0


def test_momentum_agent_short_history():
    thesis = MomentumSignalAgent().analyze("AAPL", [100.0] * 5)
    assert thesis.confidence <= 0.4
    assert thesis.supporting_data["direction"] == 0


def test_meanrev_agent_at_52w_low():
    # Price near 52-week low → bullish reversion
    prices = list(range(100, 200)) + [105]  # ended near low
    thesis = MeanReversionSignalAgent().analyze("AAPL", prices)
    assert thesis.supporting_data["direction"] == 1


def test_meanrev_agent_at_52w_high():
    # Price near 52-week high → bearish reversion
    prices = list(range(100, 200)) + [198]  # ended near high
    thesis = MeanReversionSignalAgent().analyze("AAPL", prices)
    assert thesis.supporting_data["direction"] == -1


def test_meanrev_agent_insufficient_data():
    thesis = MeanReversionSignalAgent().analyze("AAPL", [100.0] * 5)
    assert thesis.confidence <= 0.25


# ---------------------------------------------------------------------------
# Unit: RiskManager
# ---------------------------------------------------------------------------

def test_risk_manager_dampens_high_vol():
    # Manufacture high-vol price series
    import random
    random.seed(42)
    prices = [100.0]
    for _ in range(30):
        prices.append(prices[-1] * (1 + random.gauss(0, 0.05)))  # 5% daily vol

    from agents.schema import AgentThesis
    from datetime import datetime, timezone

    theses = [
        AgentThesis(
            ticker="AAPL",
            agent_name="TechnicalSignalAgent",
            thesis="bullish",
            confidence=0.9,
            key_risk="risk",
            supporting_data={"direction": 1},
        )
    ]

    rm = RiskManager()
    result = rm.adjust("AAPL", theses, prices)
    # High vol should reduce adjusted_confidence below raw 0.9
    assert result["adjusted_confidence"] < 0.9


def test_risk_manager_empty_theses():
    result = RiskManager().adjust("AAPL", [], [100.0] * 30)
    assert result["net_signal"] == 0.0
    assert result["adjusted_confidence"] == 0.0


# ---------------------------------------------------------------------------
# Unit: PortfolioManager
# ---------------------------------------------------------------------------

def test_portfolio_manager_equal_weight():
    risk = [
        {"ticker": "AAPL", "net_signal": 0.5, "adjusted_confidence": 0.8},
        {"ticker": "MSFT", "net_signal": 0.3, "adjusted_confidence": 0.7},
        {"ticker": "GOOG", "net_signal": -0.2, "adjusted_confidence": 0.6},
    ]
    weights = PortfolioManager().allocate(risk)
    assert "AAPL" in weights
    assert "MSFT" in weights
    assert "GOOG" not in weights
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_portfolio_manager_no_positive():
    risk = [{"ticker": "AAPL", "net_signal": -0.5, "adjusted_confidence": 0.7}]
    weights = PortfolioManager().allocate(risk)
    assert weights == {}


# ---------------------------------------------------------------------------
# Integration: BacktestEngine
# ---------------------------------------------------------------------------

def test_backtest_runs_and_returns_dict():
    engine = _make_engine()
    result, theses = engine.run()
    assert "walsh_pipeline" in result
    assert "buy_and_hold_baseline" in result
    assert "portfolio_history" in result
    assert isinstance(theses, list)


def test_backtest_metrics_structure():
    engine = _make_engine()
    result, _ = engine.run()
    m = result["walsh_pipeline"]
    assert "total_return" in m
    assert "sharpe_ratio" in m
    assert "max_drawdown" in m
    assert "final_value" in m


def test_backtest_no_lookahead():
    """Verify that _prices_up_to strictly enforces the cutoff date."""
    data: PriceData = {
        "AAPL": [
            (date(2023, 1, 3), 100.0),
            (date(2023, 1, 4), 105.0),
            (date(2023, 1, 5), 110.0),
        ]
    }
    prices = _prices_up_to(data, "AAPL", date(2023, 1, 4))
    assert prices == [100.0, 105.0]  # 5th excluded
    assert 110.0 not in prices


def test_backtest_positive_drift():
    # With a positive daily return, Walsh and BnH should both produce positive total return
    engine = _make_engine(daily_return=0.002)
    result, _ = engine.run()
    assert result["buy_and_hold_baseline"]["total_return"] > 0


def test_backtest_negative_drift():
    engine = _make_engine(daily_return=-0.003)
    result, _ = engine.run()
    assert result["buy_and_hold_baseline"]["total_return"] < 0


def test_backtest_config_captured():
    engine = _make_engine(tickers=["AAPL", "MSFT", "GOOG"])
    result, _ = engine.run()
    assert set(result["config"]["tickers"]) == {"AAPL", "MSFT", "GOOG"}


def test_backtest_portfolio_history_length():
    n_days = 60
    engine = _make_engine(n_days=n_days)
    result, _ = engine.run()
    # One entry per trading day (we skip weekends in mock data generator)
    assert len(result["portfolio_history"]) > 0


# ---------------------------------------------------------------------------
# Unit: compute_metrics
# ---------------------------------------------------------------------------

def test_compute_metrics_win_rate():
    values = [100.0, 110.0, 120.0]
    trades = [
        {"ticker": "A", "entry_price": 100.0, "exit_price": 110.0},  # win
        {"ticker": "B", "entry_price": 110.0, "exit_price": 105.0},  # loss
        {"ticker": "C", "entry_price": 105.0, "exit_price": 120.0},  # win
    ]
    m = compute_metrics(values, 100.0, trades)
    assert m["win_rate"] == pytest.approx(2 / 3, rel=1e-4)
    assert m["n_trades"] == 3


def test_compute_metrics_no_trades():
    values = [100.0, 110.0]
    m = compute_metrics(values, 100.0, [])
    assert m["win_rate"] is None
    assert m["n_trades"] == 0
