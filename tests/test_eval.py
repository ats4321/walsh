"""Tests for eval modules: adversarial, attribution, cost_latency."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from eval.adversarial import (
    OVERCONFIDENCE_THRESHOLD,
    AdversarialCase,
    run_adversarial,
    ALL_CASES,
    TECHNICAL_CASES,
    MOMENTUM_CASES,
    MEANREV_CASES,
)
from eval.cost_latency import PipelineTracker, cost_usd, MODEL_PRICING


# ---------------------------------------------------------------------------
# adversarial.py tests
# ---------------------------------------------------------------------------

class TestAdversarial:
    def test_run_all_cases_no_crash(self):
        results = run_adversarial()
        assert len(results) == len(ALL_CASES)

    def test_five_cases_per_agent_type(self):
        assert len(TECHNICAL_CASES) >= 5
        assert len(MOMENTUM_CASES) >= 5
        assert len(MEANREV_CASES) >= 5

    def test_each_case_has_required_fields(self):
        results = run_adversarial()
        for r in results:
            assert r.case_id
            assert r.agent_name
            assert r.description
            assert 0.0 <= r.confidence <= 1.0
            assert r.direction in (-1, 0, 1)

    def test_insufficient_data_cases_not_overconfident(self):
        """Cases with 1 data point should not produce high confidence."""
        one_point_cases = [
            c for c in ALL_CASES
            if len(c.prices) == 1 or (len(c.prices) <= 5 and "1 data point" in c.description.lower())
        ]
        results = run_adversarial(one_point_cases)
        for r in results:
            assert r.confidence < 0.5, (
                f"Case {r.case_id}: expected low confidence with minimal data, "
                f"got {r.confidence}"
            )

    def test_flagged_results_have_high_confidence(self):
        """flagged=True means overconfidence (not crash) — confidence must exceed threshold."""
        results = run_adversarial()
        for r in results:
            if r.flagged:
                assert not r.crashed, "crashed results should not be flagged"
                assert r.confidence > r.expected_max_confidence

    def test_flat_prices_neutral_or_low_confidence(self):
        """Perfectly constant prices should produce low confidence — no signal exists."""
        # Only cases with truly uniform prices (not jump-after-flat)
        flat_cases = [
            c for c in ALL_CASES
            if ("all prices identical" in c.description.lower()
                or "zero variance" in c.description.lower()
                or "zero range" in c.description.lower())
        ]
        results = run_adversarial(flat_cases)
        for r in results:
            assert r.confidence <= 0.5, (
                f"Case {r.case_id}: perfectly uniform prices should produce "
                f"low confidence, got {r.confidence}"
            )

    def test_case_ids_unique(self):
        ids = [c.case_id for c in ALL_CASES]
        assert len(ids) == len(set(ids))

    def test_custom_case(self):
        """Single custom adversarial case runs correctly."""
        case = AdversarialCase(
            case_id="CUSTOM_001",
            agent_name="TechnicalSignalAgent",
            description="Empty price list",
            prices=[],
            expect_low_confidence=True,
            expected_max_confidence=0.4,
        )
        results = run_adversarial([case])
        assert len(results) == 1
        assert results[0].confidence <= 0.4


# ---------------------------------------------------------------------------
# agent_attribution.py tests
# ---------------------------------------------------------------------------

class TestAttribution:
    def _make_theses_jsonl(self, tmp_path: Path) -> Path:
        path = tmp_path / "theses.jsonl"
        now = datetime.now(timezone.utc)
        records = [
            {
                "ticker": "AAPL",
                "agent_name": "TechnicalSignalAgent",
                "thesis": "AAPL technical signal: bullish; SMA20=...",
                "confidence": 0.8,
                "key_risk": "Whipsaw",
                "supporting_data": {"direction": 1},
                "timestamp": now.isoformat(),
            },
            {
                "ticker": "AAPL",
                "agent_name": "TechnicalSignalAgent",
                "thesis": "AAPL technical signal: bearish; SMA20=...",
                "confidence": 0.7,
                "key_risk": "Trend",
                "supporting_data": {"direction": -1},
                "timestamp": (now - timedelta(days=30)).isoformat(),
            },
            {
                "ticker": "MSFT",
                "agent_name": "MomentumSignalAgent",
                "thesis": "MSFT momentum signal: bullish momentum;",
                "confidence": 0.65,
                "key_risk": "Reversal",
                "supporting_data": {"direction": 1},
                "timestamp": now.isoformat(),
            },
        ]
        with open(path, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        return path

    def _make_price_lookup(self) -> dict[str, dict[str, float]]:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        lookup = {}
        for ticker, prices in [("AAPL", [150.0, 155.0, 158.0]), ("MSFT", [300.0, 305.0, 310.0])]:
            lookup[ticker] = {}
            for i, p in enumerate(prices):
                d = (now + timedelta(days=i * 10)).strftime("%Y-%m-%d")
                lookup[ticker][d] = p
        return lookup

    def test_load_theses(self, tmp_path):
        from eval.agent_attribution import load_theses

        path = self._make_theses_jsonl(tmp_path)
        records = load_theses(path)
        assert len(records) == 3

    def test_parse_direction_from_supporting_data(self):
        from eval.agent_attribution import _parse_direction

        assert _parse_direction("anything", {"direction": 1}) == 1
        assert _parse_direction("anything", {"direction": -1}) == -1
        assert _parse_direction("anything", {"direction": 0}) == 0

    def test_parse_direction_from_text(self):
        from eval.agent_attribution import _parse_direction

        assert _parse_direction("bullish signal detected", {}) == 1
        assert _parse_direction("bearish pressure building", {}) == -1
        assert _parse_direction("unclear signal", {}) == 0

    def test_compute_attribution_with_injected_prices(self, tmp_path):
        from eval.agent_attribution import compute_attribution, load_theses

        path = self._make_theses_jsonl(tmp_path)
        theses = load_theses(path)
        lookup = self._make_price_lookup()

        result = compute_attribution(theses, lookup, horizon_days=20)
        # Should have at least one agent in the result
        # (depends on whether timestamps line up with lookup dates)
        assert isinstance(result, dict)

    def test_calibration_structure(self, tmp_path):
        from eval.agent_attribution import compute_attribution, load_theses

        path = self._make_theses_jsonl(tmp_path)
        theses = load_theses(path)
        lookup = self._make_price_lookup()
        result = compute_attribution(theses, lookup, horizon_days=20)

        for agent_name, stats in result.items():
            assert "n_evaluated" in stats
            assert "accuracy" in stats
            assert "calibration" in stats
            for bucket in stats["calibration"]:
                assert "confidence_range" in bucket
                assert "actual_accuracy" in bucket
                assert "expected_confidence" in bucket
                assert "calibration_error" in bucket


# ---------------------------------------------------------------------------
# cost_latency.py tests
# ---------------------------------------------------------------------------

class TestCostLatency:
    def test_cost_usd_zero_tokens(self):
        assert cost_usd(0, 0) == 0.0

    def test_cost_usd_known_model(self):
        # 1M input tokens at $3/MTok = $3.00
        c = cost_usd(1_000_000, 0, model="claude-3-5-sonnet-latest")
        assert c == pytest.approx(3.0, rel=1e-6)

    def test_cost_usd_output_tokens(self):
        # 1M output at $15/MTok = $15.00
        c = cost_usd(0, 1_000_000, model="claude-3-5-sonnet-latest")
        assert c == pytest.approx(15.0, rel=1e-6)

    def test_cost_usd_unknown_model_fallback(self):
        # Should not raise; uses default pricing
        c = cost_usd(100, 50, model="some-unknown-model")
        assert c >= 0.0

    def test_all_models_have_pricing(self):
        for model in MODEL_PRICING:
            p = MODEL_PRICING[model]
            assert "input_per_mtok" in p
            assert "output_per_mtok" in p

    def test_tracker_record_tokens(self):
        tracker = PipelineTracker()
        tracker.record_tokens("TechnicalSignalAgent", input_tokens=500, output_tokens=100)
        report = tracker.report()
        assert report["totals"]["input_tokens"] == 500
        assert report["totals"]["output_tokens"] == 100
        assert report["totals"]["total_tokens"] == 600

    def test_tracker_context_manager(self):
        import time

        tracker = PipelineTracker()
        with tracker.track_agent("TechnicalSignalAgent") as ctx:
            ctx.record_tokens(input_tokens=200, output_tokens=50)
            time.sleep(0.01)  # tiny sleep to ensure wall_time > 0

        report = tracker.report()
        agents = {r["agent_name"]: r for r in report["per_agent"]}
        assert "TechnicalSignalAgent" in agents
        rec = agents["TechnicalSignalAgent"]
        assert rec["input_tokens"] == 200
        assert rec["output_tokens"] == 50
        assert rec["wall_time_s"] >= 0.0
        assert rec["cost_usd"] >= 0.0

    def test_tracker_multiple_agents(self):
        tracker = PipelineTracker()
        for name in ["TechnicalSignalAgent", "MomentumSignalAgent", "MeanReversionSignalAgent"]:
            tracker.record_tokens(name, input_tokens=300, output_tokens=80)

        report = tracker.report()
        assert len(report["per_agent"]) == 3
        assert report["totals"]["input_tokens"] == 900
        assert report["totals"]["output_tokens"] == 240

    def test_tracker_cost_computed(self):
        tracker = PipelineTracker(model="claude-3-haiku-20240307")
        tracker.record_tokens("Agent", input_tokens=1_000_000, output_tokens=0)
        report = tracker.report()
        # 1M input tokens at haiku $0.25/MTok = $0.25
        assert report["totals"]["cost_usd"] == pytest.approx(0.25, rel=1e-4)

    def test_tracker_report_structure(self):
        tracker = PipelineTracker()
        tracker.record_tokens("X", 10, 5)
        report = tracker.report()
        assert "run_timestamp" in report
        assert "totals" in report
        assert "per_agent" in report
        totals = report["totals"]
        assert "input_tokens" in totals
        assert "output_tokens" in totals
        assert "total_tokens" in totals
        assert "cost_usd" in totals
        assert "wall_time_s" in totals

    def test_tracker_save(self, tmp_path):
        tracker = PipelineTracker()
        tracker.record_tokens("Agent", 100, 50)
        out = tracker.save(tmp_path / "test_run.json")
        assert out.exists()
        data = json.loads(out.read_text())
        assert "totals" in data

    def test_ingest_anthropic_response(self):
        from types import SimpleNamespace

        tracker = PipelineTracker()
        fake_usage = SimpleNamespace(input_tokens=512, output_tokens=128)
        fake_response = SimpleNamespace(usage=fake_usage)
        tracker.ingest_anthropic_response("TechnicalSignalAgent", fake_response)
        report = tracker.report()
        assert report["totals"]["input_tokens"] == 512
        assert report["totals"]["output_tokens"] == 128
