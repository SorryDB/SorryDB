from pathlib import Path
import logging

from sorrydb.utils.verify_lean_interact import verify_lean_interact

from ..database.sorry import Sorry
from ..runners.json_runner import SorryStrategy


logger = logging.getLogger(__name__)

class RflStrategy(SorryStrategy):
    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str | None:
        return "rfl"


class SimpStrategy(SorryStrategy):
    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str | None:
        return "simp"


class NormNumStrategy(SorryStrategy):
    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str | None:
        return "norm_num"


class SingleTacticStrategy(SorryStrategy):
    """Generic strategy that returns a single tactic."""

    def __init__(self, tactic: str):
        self.tactic = tactic

    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str | None:
        return self.tactic

    def name(self):
        return self.tactic


class ProveAllStrategy(SorryStrategy):
    def __init__(self) -> None:
        super().__init__()
        # Core Lean tactics (no Mathlib required)
        self.core_tactics = [
            "rfl",
            "simp_all",
            "exact?",
        ]
        # Grind tactic (may not be available in all Lean versions)
        self.grind_tactics = [
            "grind",
        ]
        # Mathlib tactics (require Mathlib import)
        self.mathlib_tactics = [
            "ring",
            "norm_num",
            "omega",
            "linarith",
            "nlinarith",
            "aesop",
        ]

        self.tactic_lists = [self.core_tactics, self.grind_tactics, self.mathlib_tactics]

    def prove_sorry(self, repo_path: Path, sorry: Sorry)-> str | None:
        for tactic_list in self.tactic_lists:
            proof = self._prove_all(tactic_list)

            success, error_message = verify_lean_interact(
                repo_dir=repo_path,
                location=sorry.location,
                proof=proof,
            )
            if error_message:
                logger.info(f"Failed to prove with tactic list: {tactic_list}, with error: {error_message}")
            if success:
                logger.info(f"Succeeded proof with with tactic list: {tactic_list}")
                return proof

        return "sorry"

    def _prove_all(self, tactics: list[str]) -> str:
        prove_independent = " ; ".join([f"(all_goals try {t})" for t in tactics])
        prove_combined = "all_goals (" + " ; ".join([f"(try {t})" for t in tactics]) + ")"
        return "all_goals intros; first | (" + prove_independent + ") | (" + prove_combined + ")"
