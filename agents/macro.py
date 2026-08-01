"""Macro Analyst agent."""

from __future__ import annotations

import json
import re
from typing import Any

from agents.base import Agent
from agents.schema import AgentThesis
from tools.market_data import get_macro_context


class MacroAgent(Agent):
    """Analyze macro conditions that can influence a ticker."""

    agent_name = "MacroAgent"

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Walsh Macro Analyst. Evaluate the interest rate "
            "environment, inflation backdrop, sector rotation trends, the "
            "ticker's correlation and beta to broader indices, currency and "
            "geopolitical context when relevant, and macro tailwinds or "
            "headwinds for the ticker's sector. Be explicit about uncertainty "
            "when data is sparse. Return only valid JSON with keys: thesis, "
            "confidence, key_risk, supporting_data."
        )

    def build_prompt(self) -> str:
        self._macro_data = get_macro_context(self.ticker)
        data_text = json.dumps(self._macro_data or {}, indent=2, sort_keys=True)

        return (
            f"Produce a macro thesis for {self.ticker}.\n\n"
            "Use the supplied market and macro context. Focus on rates, "
            "sector rotation, index correlation, and sector-level macro "
            "tailwinds/headwinds. If fields are missing or empty, lower "
            "confidence and say what is missing.\n\n"
            f"Macro context:\n{data_text}\n\n"
            "Return JSON only in this shape:\n"
            "{\n"
            '  "thesis": "one concise paragraph",\n'
            '  "confidence": 0.0,\n'
            '  "key_risk": "main risk to the macro view",\n'
            '  "supporting_data": {"rates_view": "..."}\n'
            "}"
        )

    def parse_response(self, response: Any) -> AgentThesis:
        payload = self._load_json_response(response)
        model_supporting_data = payload.get("supporting_data") or {}
        if not isinstance(model_supporting_data, dict):
            model_supporting_data = {"model_notes": model_supporting_data}

        return AgentThesis(
            ticker=self.ticker,
            agent_name=self.agent_name,
            thesis=str(payload["thesis"]),
            confidence=float(payload["confidence"]),
            key_risk=str(payload["key_risk"]),
            supporting_data={
                "macro_data": getattr(self, "_macro_data", {}) or {},
                "model_supporting_data": model_supporting_data,
            },
        )

    def _load_json_response(self, response: Any) -> dict[str, Any]:
        text = self.response_text(response).strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = json.loads(self._extract_json_object(text))

        required = {"thesis", "confidence", "key_risk"}
        missing = required.difference(payload)
        if missing:
            missing_keys = ", ".join(sorted(missing))
            raise ValueError(f"Macro response missing required keys: {missing_keys}")

        return payload

    @staticmethod
    def _extract_json_object(text: str) -> str:
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fenced:
            return fenced.group(1)

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Macro response did not contain a JSON object")

        return text[start : end + 1]
