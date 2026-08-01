from agents.schema import AgentThesis
from orchestrator.dummy_agent_demo import DummyAgent, _FakeAnthropicClient
from tools.market_data import get_quote


def test_agent_thesis_validates_confidence_bounds() -> None:
    thesis = AgentThesis(
        ticker="aapl",
        agent_name="TestAgent",
        thesis="A test thesis.",
        confidence=0.75,
        key_risk="A test risk.",
        supporting_data={"source": "test"},
    )

    assert thesis.ticker == "AAPL"
    assert thesis.confidence == 0.75


def test_dummy_agent_runs_end_to_end_with_fake_client() -> None:
    thesis = DummyAgent("msft", client=_FakeAnthropicClient()).analyze()

    assert thesis.ticker == "MSFT"
    assert thesis.agent_name == "DummyAgent"
    assert thesis.confidence == 0.5
    assert thesis.supporting_data["quote"] == get_quote("MSFT")

