# Walsh

Walsh is a multi-agent stock research system that routes each ticker through four specialized agents in parallel — Fundamental, Technical, Sentiment, and Macro — aggregates their theses via a confidence-weighted Portfolio Manager, then gates the final call through a Rule-Based Risk Manager that can veto or downgrade before any trade is executed.

**Live demo:** [walsh-demo.vercel.app](https://demo-cyan-delta.vercel.app) · [Demo GIF](#demo)

---

## Results

Backtest run: `AAPL · MSFT · NVDA`, Jan 2023 – Dec 2023, $100k initial capital, rule-based signal agents, strict no-lookahead enforcement.

| Metric | Walsh Pipeline | Buy & Hold (equal-weight) |
|---|---|---|
| Total Return | **+75.52%** | +119.75% |
| Sharpe Ratio | **2.36** | 2.86 |
| Max Drawdown | **−13.50%** | −13.22% |
| Win Rate | **76.2%** | — |
| # Trades | **21** | — |
| Final Value | **$175,518** | $219,749 |

Walsh underperformed buy-and-hold on this bull-market period. In Oct 2023, the pipeline exited all positions when momentum signals broke down and held cash for the entire month, missing a subsequent NVDA recovery rally. This is the intended behavior of the risk gate — it correctly identified a high-uncertainty period — but reveals the cost of a conservative threshold in trending markets.

**Per-agent accuracy / confidence calibration:** pending. The `eval/agent_attribution.py` module is ready; results require ≥50 completed pipeline runs with follow-up price data to produce meaningful calibration curves.

**Cost and latency per run:** pending. The `eval/cost_latency.py` `PipelineTracker` is instrumented; numbers will be populated once the LLM-backed agents replace the current rule-based stubs.

**Adversarial robustness:** 18 test cases across three agent types; **5 flagged** for overconfidence (see [Known limitations](#known-limitations)).

---

## Architecture

```
                          ┌──────────────────────────┐
          ticker ──────►  │      Orchestrator         │
                          │   (asyncio.gather)        │
                          └──┬──┬──┬──┬──────────────┘
                             │  │  │  │  (parallel)
               ┌─────────────┘  │  │  └─────────────┐
               ▼                ▼  ▼                 ▼
        ┌────────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐
        │Fundamental │  │Technical │  │Sentiment │  │  Macro    │
        │  Analyst   │  │ Analyst  │  │ Analyst  │  │  Analyst  │
        │            │  │          │  │          │  │           │
        │PE, growth, │  │RSI, MACD,│  │news,     │  │GDP, rates,│
        │margins,    │  │golden    │  │social,   │  │inflation, │
        │D/E ratio   │  │cross     │  │insider   │  │sector     │
        └─────┬──────┘  └────┬─────┘  └────┬─────┘  └─────┬─────┘
              └──────────────┴──────────────┴──────────────┘
                                     │
                                     ▼  AgentThesis × 4
                          ┌──────────────────────┐
                          │   Portfolio Manager  │
                          │ confidence-weighted  │
                          │  signal synthesis    │
                          └──────────┬───────────┘
                                     │  PortfolioDecision
                                     ▼
                          ┌──────────────────────┐
                          │    Risk Manager      │
                          │  veto / downgrade    │
                          │  • conf < 45% → veto │
                          │  • spread ≥ 4 → veto │
                          │  • conf < 65% →      │
                          │    downgrade STRONG  │
                          └──────────┬───────────┘
                                     │  FinalDecision
                                     ▼
                              approved / vetoed
```

---

## How it works

**Fundamental Analyst** fetches valuation metrics (PE ratio, revenue growth, profit margin, debt-to-equity) and scores them against thresholds. A PE below 15 adds a bullish vote; above 30 adds a bearish one. Revenue growth above 15% or profit margins above 20% each add a bullish vote. The raw score maps to a `STRONG_BUY / BUY / HOLD / SELL / STRONG_SELL` signal with confidence proportional to conviction strength.

**Technical Analyst** evaluates SMA crossovers (20d and 50d), MACD histogram direction, and optionally a golden-cross flag. Each indicator votes +1 or −1, with a dead band to suppress spurious signals on flat prices. In the backtest harness, the rule-based `TechnicalSignalAgent` uses realized momentum over 20d and 50d rolling windows against yfinance price data.

**Sentiment Analyst** aggregates a news sentiment score (−1 to +1) and a social sentiment score, averages them, then applies an insider-buying bonus. Outputs a directional signal and a confidence value dampened for near-neutral sentiment.

**Macro Analyst** checks GDP growth, the Fed Funds rate, inflation, and a sector outlook tag. Favorable macro conditions (growth > 2.5%, rate < 4%, inflation < 3%, bullish sector) each add a bullish vote; unfavorable conditions subtract. The macro signal acts as a regime filter — a strong bearish macro can offset bullish technical or sentiment readings.

**Portfolio Manager** synthesizes the four theses using a confidence-weighted average of their numeric signal scores. Consensus penalty: confidence is scaled down by the spread between the highest and lowest agent signals (`conf × max(0.5, 1 − spread × 0.1)`). A tight consensus stays near full confidence; a 4-point spread (STRONG_BUY vs STRONG_SELL) halves it.

**Risk Manager** is the only decision-maker. Two hard veto rules: (1) portfolio confidence below 45% → forced HOLD regardless of signal, (2) agent signal spread ≥ 4 → veto as extreme disagreement. A soft rule downgrades STRONG\_BUY → BUY or STRONG\_SELL → SELL when confidence is 45–65%. If no rule fires, the decision is passed through with "No risk flags."

---

## Known limitations / failure modes

These are documented findings from `eval/adversarial.py` (18 test cases, 5 flagged):

**TECH_003 — Zigzag prices, overconfidence** (`confidence=0.80`, max expected `0.65`)
SMA signals from oscillating prices cancel imperfectly; the agent still returns 0.80 because the vote mean slightly favors one side. A price series that crosses SMA20/SMA50 repeatedly should produce near-zero confidence, but the dead band (0.1%) is too tight to suppress all noise.

**TECH_004 — Crash after uptrend, stale bullish signal** (`confidence=0.80`, max expected `0.65`)
When prices run up then crash sharply, SMA20 and SMA50 lag by construction. The agent may still read "price above SMA" for several bars after the crash top, giving a confident BUY into a falling market. The 20d momentum partially corrects this but cannot always overcome two SMA votes.

**TECH_006 — Single-day 50% jump after flat history, spurious signal** (`confidence=0.80`, max expected `0.75`)
A one-day spike inflates the 20d momentum calculation and pushes price above both SMAs immediately, generating a STRONG_BUY at 0.80 confidence despite no trend substance. Input validation (e.g., cap single-bar moves) is not currently applied.

**MOM_005 — Negative prices (data corruption), overconfident** (`confidence=0.85`, max expected `0.65`)
`MomentumSignalAgent` does not validate that prices are positive before computing log-returns. Negative prices produce a defined (if nonsensical) momentum value and a confident directional signal. A price sanity check is the fix.

**REV_006 — Zigzag mid-range, overconfident** (`confidence=0.76`, max expected `0.50`)
`MeanReversionSignalAgent` sees the price oscillating exactly in the middle of its 52-week range (no reversion signal), yet outputs 0.76 confidence. The agent currently gives a non-zero confidence for mid-range prices when it should default to "no clear reversion target."

**Structural limitations not yet tested:**
- The Risk Manager's 45% confidence threshold is a single hard cutoff; it doesn't account for drawdown regime or portfolio concentration.
- Agent signals are computed independently with no cross-agent information sharing — a macro veto doesn't lower a technical agent's confidence.
- The current backtest uses rule-based stub agents; LLM-backed agents (which can hallucinate or overstate certainty) will likely surface additional failure modes.
- No live market data integration; the orchestrator points to a mock API (`api.finance.example.com`).

---

## Demo

Live dashboard at **[demo-cyan-delta.vercel.app](https://demo-cyan-delta.vercel.app)**

The dashboard shows 5 pre-generated ticker runs (AAPL, MSFT, NVDA, TSLA, META). Use the dropdown to switch tickers. MSFT demonstrates a full Risk Manager veto — extreme disagreement between agents (Fundamental=SELL, Technical=STRONG_BUY, Macro=STRONG_SELL, Sentiment=STRONG_BUY) triggers both veto rules simultaneously.

**Terminal reproduction** (no GIF yet — recording pending):
```bash
# Run the orchestrator against mock data for MSFT:
cd demo
python3 gen_demo.py  # outputs the same JSON as demo/data/MSFT.json
```

To record the GIF once the LLM-backed pipeline is wired:
```bash
pip install vhs
vhs scripts/record_pipeline.tape  # not yet authored
```

---

## Setup

### Prerequisites

- Python 3.11+
- `uv` or `pip`
- An Anthropic API key (for the LLM-backed agents; not required for the backtest harness)

### Install

```bash
# Backtest / eval harness (walsh-backtest-eval-harness branch)
pip install -e ".[dev]"          # installs yfinance, pydantic, pytest

# Orchestrator (commit-and-push-all-changes branch)
pip install -r requirements.txt  # installs httpx
```

### Environment variables

```bash
ANTHROPIC_API_KEY=sk-ant-...   # required for LLM-backed agents
```
The backtest engine and adversarial eval do not call the Anthropic API.

### Run the backtest

```bash
python -m backtest.engine --tickers AAPL,MSFT,NVDA --start 2023-01-01 --end 2024-01-01
# Results written to eval/results/<timestamp>_backtest.json
# Agent theses appended to eval/results/theses.jsonl
```

### Run the eval suite

```bash
# Adversarial robustness (no external deps required)
python -m eval.adversarial

# Per-agent accuracy (requires theses.jsonl from a backtest run)
python -m eval.agent_attribution

# Cost / latency (requires an instrumented pipeline run)
python -m eval.cost_latency
```

### Run the full orchestrator pipeline

```bash
python -m orchestrator.main AAPL    # outputs FinalDecision JSON to stdout
```

### Tests

```bash
pytest                     # all tests
pytest tests/test_backtest.py -v
pytest tests/test_eval.py -v
```

### Run the demo dashboard locally

```bash
cd demo
npm install
npm run dev               # http://localhost:3000
```
