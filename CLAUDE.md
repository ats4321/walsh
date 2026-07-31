# Walsh Architecture

Walsh is a multi-agent trading research system. Each agent produces an
independent structured thesis for a ticker:

- Fundamental Agent: company quality, valuation, financials, filings.
- Technical Agent: price action, trend, momentum, volume, levels.
- Sentiment Agent: news, market narrative, social or analyst tone.
- Macro Agent: rates, inflation, sector, currency, geopolitical context.
- Risk Manager Agent: reviews proposed trades and can veto unacceptable risk.
- Portfolio Manager Agent: synthesizes all agent theses into the final call.

The scaffold is intentionally fake-data-only. Real API wiring for market data,
SEC filings, news, and model/tool orchestration comes later.

# Required Agent Output

All agents must output `agents.schema.AgentThesis`:

```python
AgentThesis(
    ticker=str,
    agent_name=str,
    thesis=str,
    confidence=float,  # 0.0 through 1.0
    key_risk=str,
    supporting_data=dict,
    timestamp=datetime,
)
```

# Agent Contract

Any new agent MUST subclass `agents.base.Agent` and MUST return
`agents.schema.AgentThesis` from `analyze()`.

Subclasses should implement:

- `build_prompt()` for the agent-specific prompt.
- `parse_response(response)` to convert the Anthropic response into
  `AgentThesis`.
