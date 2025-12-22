"""
Tests for running all strategies in run_morphcloud_local.py against a real sorry.

These tests verify that all strategies can be correctly instantiated and executed.
They are marked with @pytest.mark.local_only to exclude them from CI runs.

To run these tests locally:
    pytest tests/test_strategy_config.py -m local_only

To run all tests EXCEPT these:
    pytest -m "not local_only"
"""

import json
from pathlib import Path

import pytest

from sorrydb.cli.run_morphcloud_local import create_strategy_from_spec
from sorrydb.database.sorry import Sorry
from sorrydb.strategies.agentic_strategy import AgenticStrategy
from sorrydb.strategies.llm_strategy import LLMStrategy
from sorrydb.strategies.rfl_strategy import RflStrategy, SimpStrategy, ProveAllStrategy
from sorrydb.strategies.tactic_strategy import TacticByTacticStrategy
from sorrydb.utils.verify_lean_interact import verify_lean_interact


MOCK_REPO_PATH = Path(__file__).parent / "mock_lean_repository"
SORRIES_PATH = Path(__file__).parent / "mock_sorries" / "multiple_sorry.json"


def load_all_sorries() -> list[Sorry]:
    """Load all sorries from the test fixtures."""
    with open(SORRIES_PATH) as f:
        data = json.load(f)
    return [Sorry.from_dict(sorry_data) for sorry_data in data]


def sorry_id(sorry: Sorry) -> str:
    """Generate a readable test ID for a sorry."""
    return f"{sorry.location.path}:{sorry.location.start_line}:{sorry.location.start_column}"


@pytest.fixture(params=load_all_sorries(), ids=sorry_id)
def sorry(request) -> Sorry:
    """Parametrized fixture that yields each sorry from the test fixtures."""
    return request.param


@pytest.mark.local_only
class TestStrategyExecution:
    """Tests that run each strategy against a real sorry."""

    def test_rfl_strategy(self, sorry):
        """Test RFL strategy execution."""
        strategy: RflStrategy = create_strategy_from_spec('{"name": "rfl"}')
        proof = strategy.prove_sorry(MOCK_REPO_PATH, sorry)
        assert proof == "rfl"

        # Verify the proof
        is_valid, error_msg = verify_lean_interact(MOCK_REPO_PATH, sorry.location, proof)
        assert is_valid, f"Proof verification failed: {error_msg}\nProof: {proof}"

    def test_simp_strategy(self, sorry):
        """Test simp strategy execution."""
        strategy: SimpStrategy = create_strategy_from_spec('{"name": "simp"}')
        proof = strategy.prove_sorry(MOCK_REPO_PATH, sorry)
        assert proof == "simp"

        # Verify the proof
        is_valid, error_msg = verify_lean_interact(MOCK_REPO_PATH, sorry.location, proof)
        assert is_valid, f"Proof verification failed: {error_msg}\nProof: {proof}"

    def test_supersimple_strategy(self, sorry):
        """Test supersimple strategy execution (ProveAllStrategy)."""
        strategy: ProveAllStrategy = create_strategy_from_spec('{"name": "supersimple"}')
        proof = strategy.prove_sorry(MOCK_REPO_PATH, sorry)
        assert proof is not None

        # Verify the proof
        is_valid, error_msg = verify_lean_interact(MOCK_REPO_PATH, sorry.location, proof)
        assert is_valid, f"Proof verification failed: {error_msg}\nProof: {proof}"

    def test_tactic_strategy(self, sorry):
        """Test tactic strategy execution."""
        strategy: TacticByTacticStrategy = create_strategy_from_spec('{"name": "tactic", "args": {"strategy_mode": "predefined"}}')
        proof = strategy.prove_sorry(MOCK_REPO_PATH, sorry)
        assert proof is not None

        # Verify the proof
        is_valid, error_msg = verify_lean_interact(MOCK_REPO_PATH, sorry.location, proof)
        assert is_valid, f"Proof verification failed: {error_msg}\nProof: {proof}"

    def test_agentic_strategy(self, sorry):
        """Test agentic strategy execution."""
        strategy: AgenticStrategy = create_strategy_from_spec(
            '{"name": "agentic", "args": {"max_iterations": 1}}'
        )
        proof = strategy.prove_sorry(MOCK_REPO_PATH, sorry)
        assert proof is not None

        # Verify the proof
        is_valid, error_msg = verify_lean_interact(MOCK_REPO_PATH, sorry.location, proof)
        assert is_valid, f"Proof verification failed: {error_msg}\nProof: {proof}"

    def test_llm_strategy_anthropic(self, sorry):
        """Test LLM strategy with Anthropic provider."""
        strategy: LLMStrategy = create_strategy_from_spec(
            '{"name": "llm", "args": {"model_config": {"provider": "anthropic", "params": {"model": "claude-sonnet-4-5"}}}}'
        )
        proof = strategy.prove_sorry(MOCK_REPO_PATH, sorry)
        assert proof is not None

        # Verify the proof
        is_valid, error_msg = verify_lean_interact(MOCK_REPO_PATH, sorry.location, proof)
        assert is_valid, f"Proof verification failed: {error_msg}\nProof: {proof}"

    def test_llm_strategy_google(self, sorry):
        """Test LLM strategy with Google provider."""
        strategy: LLMStrategy = create_strategy_from_spec(
            '{"name": "llm", "args": {"model_config": {"provider": "google", "params": {"model": "gemini-3-flash-preview"}}}}'
        )
        proof = strategy.prove_sorry(MOCK_REPO_PATH, sorry)
        assert proof is not None

        # Verify the proof
        is_valid, error_msg = verify_lean_interact(MOCK_REPO_PATH, sorry.location, proof)
        assert is_valid, f"Proof verification failed: {error_msg}\nProof: {proof}"

    def test_llm_strategy_deepseek(self, sorry):
        """Test LLM strategy with DeepSeek provider."""
        strategy: LLMStrategy = create_strategy_from_spec(
            '{"name": "llm", "args": {"model_config": {"provider": "deepseek"}}}'
        )
        proof = strategy.prove_sorry(MOCK_REPO_PATH, sorry)
        assert proof is not None

        # Verify the proof
        is_valid, error_msg = verify_lean_interact(MOCK_REPO_PATH, sorry.location, proof)
        assert is_valid, f"Proof verification failed: {error_msg}\nProof: {proof}"

    def test_llm_strategy_kimina(self, sorry):
        """Test LLM strategy with Kimina provider."""
        strategy: LLMStrategy = create_strategy_from_spec(
            '{"name": "llm", "args": {"model_config": {"provider": "kimina"}}}'
        )
        proof = strategy.prove_sorry(MOCK_REPO_PATH, sorry)
        assert proof is not None

        # Verify the proof
        is_valid, error_msg = verify_lean_interact(MOCK_REPO_PATH, sorry.location, proof)
        assert is_valid, f"Proof verification failed: {error_msg}\nProof: {proof}"