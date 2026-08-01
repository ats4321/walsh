"""Historical backtest engine for Walsh's full multi-agent pipeline.

Replays the Walsh pipeline (signal agents → Risk Manager → Portfolio Manager)
against historical price data with strict no-lookahead enforcement.

Usage:
    python -m backtest.engine --tickers AAPL,MSFT --start 2023-01-01 --end 2024-01-01
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from agents.schema import AgentThesis

RESULTS_DIR = Path(__file__).parent.parent / "eval" / "results"
THESES_LOG = RESULTS_DIR / "theses.jsonl"

# ---------------------------------------------------------------------------
# Price data types
# ---------------------------------------------------------------------------

# {ticker: [(trading_date, adjusted_close), ...]} sorted ascending
PriceData = dict[str, list[tuple[date, float]]]


def download_prices(tickers: list[str], start: date, end: date) -> PriceData:
    """Fetch adjusted-close prices from yfinance."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError(
            "yfinance is required for live data. Install with: pip install yfinance"
        ) from exc

    result: PriceData = {}
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(
                start=start.isoformat(), end=end.isoformat()
            )
            if hist.empty:
                result[ticker] = []
                continue

            pairs: list[tuple[date, float]] = []
            for ts, price in zip(hist.index, hist["Close"]):
                d = ts.date() if hasattr(ts, "date") else ts
                if isinstance(price, float) and math.isnan(price):
                    continue
                pairs.append((d, float(price)))
            result[ticker] = sorted(pairs)
        except Exception:
            result[ticker] = []

    return result


def _price_on(data: PriceData, ticker: str, target: date) -> float | None:
    """Return the price for ticker on the closest available trading day ≤ target."""
    pairs = data.get(ticker, [])
    result: float | None = None
    for d, p in pairs:
        if d <= target:
            result = p
        else:
            break
    return result


def _prices_up_to(data: PriceData, ticker: str, cutoff: date) -> list[float]:
    """Return price series for ticker up to and including cutoff (no lookahead)."""
    return [p for d, p in data.get(ticker, []) if d <= cutoff]


def _all_trading_dates(data: PriceData) -> list[date]:
    seen: set[date] = set()
    for pairs in data.values():
        seen.update(d for d, _ in pairs)
    return sorted(seen)


def _rebalance_dates(trading_dates: list[date]) -> set[date]:
    """First trading day of each month."""
    seen_months: set[tuple[int, int]] = set()
    result: set[date] = set()
    for d in trading_dates:
        key = (d.year, d.month)
        if key not in seen_months:
            seen_months.add(key)
            result.add(d)
    return result


# ---------------------------------------------------------------------------
# Mock signal agents (deterministic, no LLM calls)
# ---------------------------------------------------------------------------

def _sma(prices: list[float], window: int) -> float | None:
    return sum(prices[-window:]) / window if len(prices) >= window else None


def _momentum(prices: list[float], period: int) -> float | None:
    if len(prices) <= period:
        return None
    prev = prices[-period - 1]
    return (prices[-1] - prev) / prev if prev != 0 else None


def _volatility_ann(prices: list[float], window: int = 20) -> float | None:
    """Annualized realized volatility from daily log-returns."""
    if len(prices) < window + 1:
        return None
    recent = prices[-(window + 1):]
    log_rets = [
        math.log(recent[i] / recent[i - 1])
        for i in range(1, len(recent))
        if recent[i - 1] > 0
    ]
    if len(log_rets) < 2:
        return None
    return statistics.stdev(log_rets) * math.sqrt(252)


class TechnicalSignalAgent:
    """SMA crossover + momentum → direction and confidence."""

    agent_name = "TechnicalSignalAgent"

    def analyze(self, ticker: str, prices: list[float]) -> AgentThesis:
        sma20 = _sma(prices, 20)
        sma50 = _sma(prices, 50)
        mom20 = _momentum(prices, 20)
        last = prices[-1] if prices else None

        votes: list[int] = []
        # Use 0.1% band so perfectly flat prices don't generate a spurious bearish vote
        if sma20 and last:
            if last > sma20 * 1.001:
                votes.append(1)
            elif last < sma20 * 0.999:
                votes.append(-1)
        if sma50 and last:
            if last > sma50 * 1.001:
                votes.append(1)
            elif last < sma50 * 0.999:
                votes.append(-1)
        if mom20 is not None and abs(mom20) > 0.001:  # ignore near-zero momentum
            votes.append(1 if mom20 > 0 else -1)

        if not votes or last is None:
            direction, confidence = 0, 0.25
            summary = "insufficient data"
        else:
            mean_vote = sum(votes) / len(votes)
            direction = 1 if mean_vote > 0.3 else (-1 if mean_vote < -0.3 else 0)
            confidence = round(min(0.9, 0.45 + abs(mean_vote) * 0.35), 4)
            label = "bullish" if direction > 0 else ("bearish" if direction < 0 else "neutral")
            sma50_s = f"{sma50:.2f}" if sma50 is not None else "N/A"
            mom20_s = f"{mom20:.2%}" if mom20 is not None else "N/A"
            summary = f"{label}; SMA20={sma20:.2f}, SMA50={sma50_s}, mom20={mom20_s}"

        return AgentThesis(
            ticker=ticker,
            agent_name=self.agent_name,
            thesis=f"{ticker} technical signal: {summary}.",
            confidence=confidence,
            key_risk="SMA signals lag; can whipsaw in range-bound markets.",
            supporting_data={
                "direction": direction,
                "sma20": sma20,
                "sma50": sma50,
                "momentum_20d": mom20,
                "last_price": last,
            },
        )


class MomentumSignalAgent:
    """3-month and 12-month return momentum factor."""

    agent_name = "MomentumSignalAgent"

    def analyze(self, ticker: str, prices: list[float]) -> AgentThesis:
        mom63 = _momentum(prices, 63)   # ~3 months
        mom252 = _momentum(prices, 252)  # ~12 months
        last = prices[-1] if prices else None

        votes: list[int] = []
        if mom63 is not None:
            votes.append(1 if mom63 > 0 else -1)
        if mom252 is not None:
            votes.append(1 if mom252 > 0 else -1)

        if not votes:
            direction, confidence = 0, 0.25
            summary = "insufficient history for momentum"
        else:
            mean_vote = sum(votes) / len(votes)
            direction = 1 if mean_vote > 0 else (-1 if mean_vote < 0 else 0)
            # Strong momentum = higher confidence
            strengths = [abs(m) for m in [mom63, mom252] if m is not None]
            avg_strength = sum(strengths) / len(strengths)
            confidence = round(min(0.9, 0.4 + min(avg_strength, 0.5) * 0.9), 4)
            label = "bullish" if direction > 0 else "bearish"
            m63_s = f"{mom63:.2%}" if mom63 is not None else "N/A"
            m252_s = f"{mom252:.2%}" if mom252 is not None else "N/A"
            summary = f"{label} momentum; 3m={m63_s}, 12m={m252_s}"

        return AgentThesis(
            ticker=ticker,
            agent_name=self.agent_name,
            thesis=f"{ticker} momentum signal: {summary}.",
            confidence=confidence,
            key_risk="Momentum crashes during sharp reversals.",
            supporting_data={
                "direction": direction,
                "momentum_63d": mom63,
                "momentum_252d": mom252,
                "last_price": last,
            },
        )


class MeanReversionSignalAgent:
    """Contrarian signal: distance from 52-week high/low."""

    agent_name = "MeanReversionSignalAgent"

    def analyze(self, ticker: str, prices: list[float]) -> AgentThesis:
        window = min(252, len(prices))
        if window < 20 or not prices:
            return AgentThesis(
                ticker=ticker,
                agent_name=self.agent_name,
                thesis=f"{ticker} mean-reversion: insufficient history.",
                confidence=0.2,
                key_risk="Insufficient data.",
                supporting_data={"direction": 0},
            )

        recent = prices[-window:]
        high52 = max(recent)
        low52 = min(recent)
        last = prices[-1]
        rng = high52 - low52

        if rng == 0:
            direction, confidence = 0, 0.2
            summary = "no range, signal flat"
        else:
            pct_from_high = (high52 - last) / rng  # 0 = at high, 1 = at low
            # Mean reversion: buy when near low (pct_from_high > 0.7), sell when near high
            if pct_from_high > 0.7:
                direction = 1
                confidence = round(min(0.8, 0.4 + (pct_from_high - 0.7) * 1.2), 4)
                summary = f"bullish reversion; {pct_from_high:.0%} off 52w high"
            elif pct_from_high < 0.3:
                direction = -1
                confidence = round(min(0.8, 0.4 + (0.3 - pct_from_high) * 1.2), 4)
                summary = f"bearish reversion; only {pct_from_high:.0%} off 52w high"
            else:
                direction = 0
                confidence = 0.3
                summary = "neutral; mid-range"

        return AgentThesis(
            ticker=ticker,
            agent_name=self.agent_name,
            thesis=f"{ticker} mean-reversion signal: {summary}.",
            confidence=confidence,
            key_risk="Reversion can fail in trending markets.",
            supporting_data={
                "direction": direction,
                "high_52w": high52,
                "low_52w": low52,
                "last_price": last,
            },
        )


# ---------------------------------------------------------------------------
# Risk Manager
# ---------------------------------------------------------------------------

class RiskManager:
    """Volatility-adjusts aggregate signal. High vol → dampen confidence."""

    vol_cap = 0.40  # 40% annualized vol caps confidence to 0.5

    def adjust(
        self, ticker: str, theses: list[AgentThesis], prices: list[float]
    ) -> dict[str, Any]:
        directions = [int(t.supporting_data.get("direction", 0)) for t in theses]
        confidences = [t.confidence for t in theses]

        if not directions:
            return {"ticker": ticker, "net_signal": 0.0, "adjusted_confidence": 0.0}

        # Confidence-weighted aggregate direction
        weighted = sum(d * c for d, c in zip(directions, confidences))
        total_conf = sum(confidences)
        net_signal = weighted / total_conf if total_conf else 0.0

        # Dampen by realized volatility
        vol = _volatility_ann(prices)
        vol_dampen = max(0.0, 1.0 - (vol or 0.0) / self.vol_cap)
        adj_confidence = round(min(0.9, (total_conf / len(confidences)) * vol_dampen), 4)

        return {
            "ticker": ticker,
            "net_signal": round(net_signal, 4),
            "adjusted_confidence": adj_confidence,
            "realized_vol_ann": round(vol, 4) if vol else None,
        }


# ---------------------------------------------------------------------------
# Portfolio Manager
# ---------------------------------------------------------------------------

class PortfolioManager:
    """Allocate equal weight to positive-net-signal tickers."""

    def allocate(self, risk_assessments: list[dict[str, Any]]) -> dict[str, float]:
        positive = [r for r in risk_assessments if r["net_signal"] > 0]
        if not positive:
            return {}
        weight = 1.0 / len(positive)
        return {r["ticker"]: weight for r in positive}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _daily_returns(values: list[float]) -> list[float]:
    return [
        (values[i] - values[i - 1]) / values[i - 1]
        for i in range(1, len(values))
        if values[i - 1] != 0
    ]


def _sharpe(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    mu = statistics.mean(returns)
    sigma = statistics.stdev(returns)
    return round(mu / sigma * math.sqrt(252), 4) if sigma else None


def _max_drawdown(values: list[float]) -> float:
    peak = values[0]
    max_dd = 0.0
    for v in values:
        peak = max(peak, v)
        dd = (peak - v) / peak if peak else 0.0
        max_dd = max(max_dd, dd)
    return round(max_dd, 6)


def compute_metrics(
    daily_values: list[float],
    initial_capital: float,
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    total_return = (daily_values[-1] - initial_capital) / initial_capital
    rets = _daily_returns(daily_values)
    win_trades = [t for t in trades if t["exit_price"] > t["entry_price"]]
    win_rate = len(win_trades) / len(trades) if trades else None

    return {
        "total_return": round(total_return, 6),
        "total_return_pct": f"{total_return:.2%}",
        "sharpe_ratio": _sharpe(rets),
        "max_drawdown": _max_drawdown(daily_values),
        "max_drawdown_pct": f"{_max_drawdown(daily_values):.2%}",
        "win_rate": round(win_rate, 4) if win_rate is not None else None,
        "n_trades": len(trades),
        "final_value": round(daily_values[-1], 2),
    }


# ---------------------------------------------------------------------------
# Buy-and-Hold baseline
# ---------------------------------------------------------------------------

def compute_bnh_metrics(
    data: PriceData,
    all_dates: list[date],
    tickers: list[str],
    initial_capital: float,
) -> dict[str, Any]:
    """Equal-weight buy-and-hold across all tickers."""
    first, last = all_dates[0], all_dates[-1]
    valid = [t for t in tickers if _price_on(data, t, first) and _price_on(data, t, last)]
    if not valid:
        return {"error": "No valid tickers for baseline."}

    # Build daily value series
    daily_values: list[float] = []
    for d in all_dates:
        prices = [_price_on(data, t, d) for t in valid]
        prices = [p for p in prices if p is not None]
        if not prices:
            continue
        # Equal-weight normalized return: (avg_price / avg_first_price) * capital
        first_prices = [_price_on(data, t, first) for t in valid]
        first_prices = [p for p in first_prices if p is not None]
        avg_return = sum(
            (_price_on(data, t, d) or f) / f
            for t, f in zip(valid, first_prices)
        ) / len(valid)
        daily_values.append(initial_capital * avg_return)

    if not daily_values:
        return {"error": "No price data for baseline."}

    total_return = (daily_values[-1] - initial_capital) / initial_capital
    rets = _daily_returns(daily_values)

    return {
        "total_return": round(total_return, 6),
        "total_return_pct": f"{total_return:.2%}",
        "sharpe_ratio": _sharpe(rets),
        "max_drawdown": _max_drawdown(daily_values),
        "max_drawdown_pct": f"{_max_drawdown(daily_values):.2%}",
        "final_value": round(daily_values[-1], 2),
    }


# ---------------------------------------------------------------------------
# Backtest Engine
# ---------------------------------------------------------------------------

class BacktestEngine:
    """
    Replays the Walsh multi-agent pipeline against historical data.

    data_provider: injectable for testing; defaults to yfinance download.
    """

    def __init__(
        self,
        tickers: list[str],
        start: date,
        end: date,
        initial_capital: float = 100_000.0,
        data_provider: Callable[[list[str], date, date], PriceData] | None = None,
    ) -> None:
        self.tickers = [t.strip().upper() for t in tickers]
        self.start = start
        self.end = end
        self.initial_capital = initial_capital
        self._data_provider = data_provider or download_prices

        self._agents = [
            TechnicalSignalAgent(),
            MomentumSignalAgent(),
            MeanReversionSignalAgent(),
        ]
        self._risk_mgr = RiskManager()
        self._port_mgr = PortfolioManager()

    def run(self) -> dict[str, Any]:
        data = self._data_provider(self.tickers, self.start, self.end)
        all_dates = _all_trading_dates(data)
        if len(all_dates) < 2:
            raise ValueError("Not enough trading days in the requested range.")

        rebalance_set = _rebalance_dates(all_dates)

        portfolio_value = self.initial_capital
        daily_values: list[float] = [self.initial_capital]
        positions: dict[str, float] = {}   # {ticker: portfolio_fraction}
        entry_prices: dict[str, float] = {}
        trades: list[dict[str, Any]] = []
        all_theses: list[dict[str, Any]] = []

        for i in range(1, len(all_dates)):
            prev_date = all_dates[i - 1]
            curr_date = all_dates[i]

            if curr_date in rebalance_set:
                # Close existing positions → record trades
                for ticker, weight in positions.items():
                    entry = entry_prices.get(ticker)
                    exit_p = _price_on(data, ticker, curr_date)
                    if entry and exit_p:
                        trades.append({
                            "ticker": ticker,
                            "entry_price": entry,
                            "exit_price": exit_p,
                            "weight": weight,
                        })

                # Run pipeline for each ticker (no lookahead: data up to curr_date)
                risk_inputs: list[dict[str, Any]] = []
                for ticker in self.tickers:
                    prices = _prices_up_to(data, ticker, curr_date)
                    if len(prices) < 2:
                        continue
                    theses = [a.analyze(ticker, prices) for a in self._agents]
                    for t in theses:
                        all_theses.append(t.model_dump(mode="json"))
                    risk_result = self._risk_mgr.adjust(ticker, theses, prices)
                    risk_inputs.append(risk_result)

                # Portfolio manager → new weights
                new_weights = self._port_mgr.allocate(risk_inputs)
                positions = new_weights
                entry_prices = {
                    t: _price_on(data, t, curr_date) or 0.0
                    for t in new_weights
                }

            # Update portfolio value based on today's price moves
            daily_return = 0.0
            for ticker, weight in positions.items():
                prev_price = _price_on(data, ticker, prev_date)
                curr_price = _price_on(data, ticker, curr_date)
                if prev_price and curr_price and prev_price != 0:
                    daily_return += weight * (curr_price - prev_price) / prev_price

            portfolio_value *= 1 + daily_return
            daily_values.append(portfolio_value)

        metrics = compute_metrics(daily_values, self.initial_capital, trades)
        baseline = compute_bnh_metrics(data, all_dates, self.tickers, self.initial_capital)

        return {
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "config": {
                "tickers": self.tickers,
                "start": self.start.isoformat(),
                "end": self.end.isoformat(),
                "initial_capital": self.initial_capital,
            },
            "walsh_pipeline": metrics,
            "buy_and_hold_baseline": baseline,
            "portfolio_history": [
                {"date": all_dates[i].isoformat(), "value": round(daily_values[i], 2)}
                for i in range(len(all_dates))
            ],
            "agent_theses_count": len(all_theses),
        }, all_theses


def _print_summary(result: dict[str, Any]) -> None:
    cfg = result["config"]
    w = result["walsh_pipeline"]
    b = result["buy_and_hold_baseline"]
    sep = "=" * 58

    print(f"\nWalsh Backtest: {', '.join(cfg['tickers'])} | {cfg['start']} to {cfg['end']}")
    print(sep)
    print(f"{'Metric':<22} {'Walsh Pipeline':>16} {'Buy & Hold':>16}")
    print("-" * 58)

    def row(label: str, wval: Any, bval: Any) -> None:
        print(f"{label:<22} {str(wval):>16} {str(bval):>16}")

    row("Total Return", w.get("total_return_pct", "N/A"), b.get("total_return_pct", "N/A"))
    row("Sharpe Ratio", w.get("sharpe_ratio", "N/A"), b.get("sharpe_ratio", "N/A"))
    row("Max Drawdown", w.get("max_drawdown_pct", "N/A"), b.get("max_drawdown_pct", "N/A"))
    row("Win Rate", w.get("win_rate", "N/A"), "N/A")
    row("# Trades", w.get("n_trades", "N/A"), "N/A")
    row("Final Value", f"${w.get('final_value', 0):,.2f}", f"${b.get('final_value', 0):,.2f}")
    print(sep)


def _save_result(result: dict[str, Any], theses: list[dict[str, Any]]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"{ts}_backtest.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))

    # Append theses to shared JSONL store for agent_attribution use
    with THESES_LOG.open("a") as f:
        for t in theses:
            f.write(json.dumps(t, default=str) + "\n")

    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Walsh historical backtest")
    parser.add_argument(
        "--tickers", required=True, help="Comma-separated tickers, e.g. AAPL,MSFT"
    )
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument(
        "--capital", type=float, default=100_000.0, help="Initial capital (default 100000)"
    )
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",")]
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    engine = BacktestEngine(tickers, start, end, initial_capital=args.capital)
    result, theses = engine.run()

    _print_summary(result)
    saved = _save_result(result, theses)
    print(f"\nResults saved to {saved}")
    print(f"Theses appended to {THESES_LOG}")
