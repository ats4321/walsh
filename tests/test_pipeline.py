"""End-to-end integration test for the orchestrator pipeline.

Mocks the market-data API seam so the full fan-out -> PM -> risk-gate flow is
exercised deterministically. Run: python -m unittest discover -s tests
"""

import unittest
from unittest.mock import AsyncMock, patch

from orchestrator.main import orchestrate, BUY, SELL, HOLD


def _patch_feeds(fundamentals, prices, news, macro):
    """Patch all four fetchers with AsyncMocks; returns a list of patchers."""
    return [
        patch("orchestrator.main.fetch_fundamentals",
              new=AsyncMock(return_value=fundamentals)),
        patch("orchestrator.main.fetch_prices",
              new=AsyncMock(return_value=prices)),
        patch("orchestrator.main.fetch_news",
              new=AsyncMock(return_value=news)),
        patch("orchestrator.main.fetch_macro",
              new=AsyncMock(return_value=macro)),
    ]


class TestPipeline(unittest.IsolatedAsyncioTestCase):

    async def _run(self, fundamentals, prices, news, macro):
        from orchestrator.main import MemoryStore
        memory = MemoryStore()
        patchers = _patch_feeds(fundamentals, prices, news, macro)
        for p in patchers:
            p.start()
        try:
            decision = await orchestrate("aapl", memory)
        finally:
            for p in patchers:
                p.stop()
        return decision, memory

    async def test_full_pipeline_bullish_buy(self):
        decision, memory = await self._run(
            fundamentals={"pe_ratio": 18, "revenue_growth": 0.25},
            prices={"momentum": 0.8, "rsi": 55},
            news={"sentiment_score": 0.7},
            macro={"regime": "expansion"},
        )

        self.assertEqual(decision.action, BUY)
        self.assertEqual(decision.proposed_action, BUY)
        self.assertTrue(decision.approved)
        self.assertEqual(decision.ticker, "AAPL")
        self.assertGreater(decision.confidence, 0.35)

        # every stage logged everything to memory: start + 4 theses + proposal + decision
        kinds = [e["kind"] for e in memory.by_ticker("AAPL")]
        self.assertEqual(kinds.count("thesis"), 4)
        self.assertEqual(kinds.count("start"), 1)
        self.assertEqual(kinds.count("proposal"), 1)
        self.assertEqual(kinds.count("decision"), 1)
        self.assertEqual(len(decision.theses), 4)

    async def test_risk_gate_vetoes_buy_on_macro_headwind(self):
        # Analysts lean bullish enough to propose BUY, but macro says recession.
        decision, _ = await self._run(
            fundamentals={"pe_ratio": 18, "revenue_growth": 0.25},
            prices={"momentum": 0.9, "rsi": 55},
            news={"sentiment_score": 0.9},
            macro={"regime": "recession"},
        )
        self.assertEqual(decision.proposed_action, BUY)
        self.assertFalse(decision.approved)
        self.assertEqual(decision.action, HOLD)
        self.assertIn("macro", decision.rationale.lower())

    async def test_bearish_sell(self):
        decision, _ = await self._run(
            fundamentals={"pe_ratio": 60, "revenue_growth": -0.2},
            prices={"momentum": -0.9, "rsi": 80},
            news={"sentiment_score": -0.8},
            macro={"regime": "recession"},
        )
        self.assertEqual(decision.action, SELL)
        self.assertTrue(decision.approved)


if __name__ == "__main__":
    unittest.main()
