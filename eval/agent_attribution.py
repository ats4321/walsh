"""Per-agent thesis accuracy and confidence-calibration scoring.

Pulls AgentThesis records from the JSONL memory store (written by
backtest/engine.py) and checks whether each agent's bullish/bearish
direction correlated with subsequent actual price movement.

Usage:
    python -m eval.agent_attribution [--theses PATH] [--horizon-days N]
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).parent / "results"
DEFAULT_THESES = RESULTS_DIR / "theses.jsonl"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_theses(path: Path) -> list[dict[str, Any]]:
    """Load AgentThesis records from a JSONL file."""
    records: list[dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_price_lookup(path: Path) -> dict[str, dict[str, float]]:
    """
    Load {ticker: {date_str: price}} from a backtest result JSON
    (portfolio_history gives Walsh values; we need per-ticker prices).

    If a dedicated price file doesn't exist, returns empty — attribution
    will download prices on the fly via yfinance.
    """
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return data.get("ticker_prices", {})


# ---------------------------------------------------------------------------
# Direction extraction
# ---------------------------------------------------------------------------

def _parse_direction(thesis: str, supporting_data: dict[str, Any]) -> int:
    """Return +1 (bullish), -1 (bearish), or 0 (neutral/unknown)."""
    if "direction" in supporting_data:
        try:
            return int(supporting_data["direction"])
        except (TypeError, ValueError):
            pass
    text = thesis.lower()
    if "bullish" in text:
        return 1
    if "bearish" in text:
        return -1
    return 0


def _parse_dt(timestamp: Any) -> datetime | None:
    if isinstance(timestamp, datetime):
        return timestamp
    if not isinstance(timestamp, str):
        return None
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Price lookup helpers (yfinance fallback)
# ---------------------------------------------------------------------------

def _build_price_lookup_yf(
    tickers: list[str], start: datetime, end: datetime
) -> dict[str, dict[str, float]]:
    """Download price data and return {ticker: {YYYY-MM-DD: price}}."""
    try:
        import yfinance as yf
    except ImportError:
        return {}

    lookup: dict[str, dict[str, float]] = {}
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(
                start=start.date().isoformat(),
                end=(end.date() + timedelta(days=5)).isoformat(),
            )
            lookup[ticker] = {
                ts.strftime("%Y-%m-%d"): float(price)
                for ts, price in zip(hist.index, hist["Close"])
                if not (isinstance(price, float) and math.isnan(price))
            }
        except Exception:
            lookup[ticker] = {}

    return lookup


def _price_on_or_after(prices: dict[str, float], target: datetime) -> float | None:
    target_str = target.strftime("%Y-%m-%d")
    for d in sorted(prices):
        if d >= target_str:
            return prices[d]
    return None


# ---------------------------------------------------------------------------
# Attribution core
# ---------------------------------------------------------------------------

def compute_attribution(
    theses: list[dict[str, Any]],
    price_lookup: dict[str, dict[str, float]],
    horizon_days: int = 20,
) -> dict[str, Any]:
    """
    For each non-neutral thesis, check if direction matched subsequent price move.

    Returns per-agent accuracy and confidence-calibration stats.
    """
    agent_data: dict[str, list[dict[str, Any]]] = {}

    for record in theses:
        ticker = record.get("ticker", "")
        agent_name = record.get("agent_name", "unknown")
        confidence = float(record.get("confidence", 0.0))
        thesis_text = record.get("thesis", "")
        supporting = record.get("supporting_data", {})
        direction = _parse_direction(thesis_text, supporting)

        if direction == 0:
            continue  # Skip neutral — no directional claim to evaluate

        ts = _parse_dt(record.get("timestamp"))
        if ts is None:
            continue

        prices = price_lookup.get(ticker, {})
        entry = _price_on_or_after(prices, ts)
        exit_target = ts + timedelta(days=horizon_days)
        exit_p = _price_on_or_after(prices, exit_target)

        if entry is None or exit_p is None:
            continue

        actual_return = (exit_p - entry) / entry if entry != 0 else 0.0
        actual_dir = 1 if actual_return > 0 else -1
        correct = direction == actual_dir

        agent_data.setdefault(agent_name, []).append(
            {
                "ticker": ticker,
                "direction": direction,
                "confidence": confidence,
                "actual_return": actual_return,
                "correct": correct,
            }
        )

    summary: dict[str, Any] = {}
    for agent_name, results in agent_data.items():
        n = len(results)
        accuracy = sum(1 for r in results if r["correct"]) / n if n else 0.0
        summary[agent_name] = {
            "n_evaluated": n,
            "accuracy": round(accuracy, 4),
            "calibration": _calibrate(results),
        }

    return summary


def _calibrate(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bucket by confidence decile and compare expected vs actual accuracy."""
    bins: dict[int, list[bool]] = {}
    for r in results:
        bucket = min(9, int(r["confidence"] * 10))
        bins.setdefault(bucket, []).append(r["correct"])

    calibration = []
    for bucket in sorted(bins):
        bucket_results = bins[bucket]
        n = len(bucket_results)
        actual_acc = sum(bucket_results) / n
        # Expected: midpoint of bucket (e.g. bucket 8 → 85% confidence)
        expected = (bucket * 10 + 5) / 100
        calibration.append(
            {
                "confidence_range": f"{bucket * 10}%–{bucket * 10 + 10}%",
                "n": n,
                "actual_accuracy": round(actual_acc, 4),
                "expected_confidence": round(expected, 4),
                "calibration_error": round(abs(actual_acc - expected), 4),
            }
        )
    return calibration


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_attribution(
    theses_path: Path = DEFAULT_THESES,
    horizon_days: int = 20,
    price_lookup: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    if not theses_path.exists():
        raise FileNotFoundError(
            f"Theses file not found: {theses_path}. "
            "Run `python -m backtest.engine` first to populate it."
        )

    theses = load_theses(theses_path)

    if price_lookup is None:
        # Build lookup from thesis timestamps
        tickers = list({r.get("ticker", "") for r in theses if r.get("ticker")})
        timestamps = [_parse_dt(r.get("timestamp")) for r in theses]
        valid_ts = [t for t in timestamps if t is not None]
        if valid_ts:
            ts_start = min(valid_ts) - timedelta(days=1)
            ts_end = max(valid_ts) + timedelta(days=horizon_days + 10)
            price_lookup = _build_price_lookup_yf(tickers, ts_start, ts_end)
        else:
            price_lookup = {}

    result = compute_attribution(theses, price_lookup, horizon_days=horizon_days)

    # Save to results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"{ts}_attribution.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"Attribution saved to {out_path}")

    _print_attribution(result)
    return result


def _print_attribution(result: dict[str, Any]) -> None:
    print("\n=== Agent Attribution ===")
    for agent, stats in result.items():
        n = stats["n_evaluated"]
        acc = stats["accuracy"]
        cal = stats["calibration"]
        avg_err = statistics.mean(c["calibration_error"] for c in cal) if cal else None
        print(
            f"  {agent}: n={n}, accuracy={acc:.1%}, "
            f"avg_calibration_error={avg_err:.3f}" if avg_err is not None else f"  {agent}: n={n}, accuracy={acc:.1%}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Walsh agent attribution scoring")
    parser.add_argument("--theses", default=str(DEFAULT_THESES), help="Path to theses JSONL")
    parser.add_argument("--horizon-days", type=int, default=20, help="Evaluation horizon in trading days")
    args = parser.parse_args()
    run_attribution(Path(args.theses), horizon_days=args.horizon_days)
