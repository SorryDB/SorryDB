import asyncio
import logging
from pathlib import Path

import aristotlelib

from sorrydb.database.sorry import Sorry
from sorrydb.runners.json_runner import SorryStrategy
from sorrydb.strategies.llm_proof_utils import (
    extract_proof_from_code_block,
    extract_proof_from_full_theorem_statement,
)

logger = logging.getLogger(__name__)


class AristotleStrategy(SorryStrategy):
    """Strategy that uses Aristotle's theorem proving service via aristotlelib."""

    def __init__(self):
        pass

    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str | None:
        """Prove a sorry using Aristotle's API.

        Args:
            repo_path: Path to the Lean repository
            sorry: The sorry to prove

        Returns:
            Proof string or None if no proof found
        """
        return asyncio.run(self._prove_sorry_async(repo_path, sorry))

    async def prove_sorry_async(self, repo_path: Path, sorry: Sorry) -> str | None:
        """Async version for parallel execution support."""
        return await self._prove_sorry_async(repo_path, sorry)

    async def _prove_sorry_async(self, repo_path: Path, sorry: Sorry) -> str | None:
        loc = sorry.location
        file_path = repo_path / loc.path

        try:
            # Use aristotlelib's prove_from_file convenience method
            # which handles import resolution automatically
            solution_path = await aristotlelib.Project.prove_from_file(
                input_file_path=str(file_path)
            )

            if solution_path:
                # Read the solution file and extract the proof
                solution_text = Path(solution_path).read_text()
                proof = self._extract_proof(solution_text, sorry)
                return proof

            return None

        except Exception as e:
            logger.error(f"Aristotle API error: {type(e).__name__}: {e}")
            return None

    def _extract_proof(self, solution_text: str, sorry: Sorry) -> str | None:
        """Extract the proof portion that replaces the sorry."""
        # Use existing extraction utilities
        proof = extract_proof_from_code_block(solution_text)
        proof = extract_proof_from_full_theorem_statement(proof)
        return proof if proof else None

    def name(self) -> str:
        return "AristotleStrategy"
