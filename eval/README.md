# Walsh Eval Harness

Four modules for validating Walsh's multi-agent trading pipeline: historical backtesting, per-agent accuracy scoring, adversarial robustness testing, and cost/latency profiling.

All results are written to `eval/results/` as timestamped JSON files so they can be diffed across runs.

---

## Modules

### `backtest/engine.py` — Historical Backtest

Replays the full Walsh pipeline (signal agents → Risk Manager → Portfolio Manager) against historical price data. Strict no-lookahead enforcement: each simulation date only uses data available at that point in time.

**Agents simulated:**
- `TechnicalSignalAgent` — SMA crossover + 20d momentum
- `MomentumSignalAgent` — 3-month and 12-month return factors
- `MeanReversionSignalAgent` — distance from 52-week high/low

**Metrics computed:** total return, Sharpe ratio, max drawdown, win rate, trade count.

**Buy-and-hold baseline:** equal-weight across all tickers, recomputed daily.

```bash
python -m backtest.engine --tickers AAPL,MSFT --start 2023-01-01 --end 2024-01-01
python -m backtest.engine --tickers AAPL,MSFT,GOOG --start 2022-01-01 --end 2024-01-01 --capital 500000
```

Agent theses are appended to `eval/results/theses.jsonl` (JSONL memory store) after each run for use by `agent_attribution.py`.

---

### `eval/agent_attribution.py` — Per-Agent Accuracy

Reads `AgentThesis` records from the JSONL memory store and checks whether each agent's directional thesis (bullish/bearish) correlated with the actual subsequent price movement over a configurable horizon.

**Reports:**
- Accuracy per agent (% of directional theses that were correct)
- Confidence calibration: when an agent said 90% confidence, was it right ~90% of the time?

Requires `eval/results/theses.jsonl` to exist (populated by the backtest engine).

```bash
python -m eval.agent_attribution
python -m eval.agent_attribution --theses eval/results/theses.jsonl --horizon-days 20
```

```python
from eval.agent_attribution import run_attribution
result = run_attribution(horizon_days=20)
```

---

### `eval/adversarial.py` — Robustness Tests

Feeds each agent deliberately degenerate, contradictory, or ambiguous price inputs and flags cases where confidence stays high despite bad input (overconfidence / hallucination check).

**Test cases (18 total, 6 per agent type):**

| Agent | Cases |
|-------|-------|
| TechnicalSignalAgent | Single data point, flat prices, zigzag, crash-then-recover, contradictory SMA/momentum, spurious jump |
| MomentumSignalAgent | Tiny history, flat prices, trend reversal, 200d zigzag, negative prices, crash-then-recover |
| MeanReversionSignalAgent | < 20 days, zero range, midpoint, persistent downtrend, zero prices, zigzag |

A case is **flagged** if the agent's `confidence` exceeds the `expected_max_confidence` threshold for that case.

```bash
python -m eval.adversarial
```

```python
from eval.adversarial import run_adversarial, ALL_CASES
results = run_adversarial()
flagged = [r for r in results if r.flagged]
```

---

### `eval/cost_latency.py` — Cost & Latency Tracking

Tracks per-agent token usage and wall-clock time for a full pipeline run and reports estimated API cost using Anthropic's published pricing.

**Supported models (pricing table built-in):**
- claude-3-5-sonnet-latest / claude-sonnet-4-6
- claude-3-haiku-20240307 / claude-haiku-4-5-20251001
- claude-3-opus-20240229 / claude-opus-4-8

```python
from eval.cost_latency import PipelineTracker

tracker = PipelineTracker()

# Option 1: context manager (measures wall time automatically)
with tracker.track_agent("TechnicalSignalAgent") as ctx:
    response = agent.analyze()
    ctx.record_tokens(input_tokens=512, output_tokens=128)

# Option 2: ingest Anthropic SDK response directly
tracker.ingest_anthropic_response("MomentumSignalAgent", anthropic_response)

tracker.print_summary()
report = tracker.report()         # dict with totals + per-agent breakdown
saved = tracker.save()            # writes to eval/results/<timestamp>_cost_latency.json
```

---

## Running Tests

```bash
# Install dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with verbose output
pytest -v
```

---

## Output Files

| File | Written by | Contents |
|------|-----------|----------|
| `eval/results/<ts>_backtest.json` | `backtest/engine.py` | Metrics, baseline, portfolio history |
| `eval/results/theses.jsonl` | `backtest/engine.py` | All agent theses (JSONL, append-only) |
| `eval/results/<ts>_attribution.json` | `agent_attribution.py` | Per-agent accuracy + calibration |
| `eval/results/<ts>_adversarial.json` | `adversarial.py` | All adversarial test results + flags |
| `eval/results/<ts>_cost_latency.json` | `cost_latency.py` | Token counts + costs + timing |
