from pathlib import Path

from ..database.sorry import Proof, Sorry
from ..utils.verify import verify_proof
from ..runners.json_runner import SorryStrategy

class RflStrategy(SorryStrategy):
    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> Proof | None:
        return Proof(proof="rfl")


class SimpStrategy(SorryStrategy):
    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> Proof | None:
        return Proof(proof="simp")


class NormNumStrategy(SorryStrategy):
    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> Proof | None:
        return Proof(proof="norm_num")


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

    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> Proof | None:
        for tactic_list in self.tactic_lists:
            proof = Proof(proof=self._prove_all(tactic_list))
            success, error_message = verify_proof(
                repo_dir=repo_path,
                lean_version=sorry.repo.lean_version,
                location=sorry.location,
                proof=proof,
            )
            if success:
                return proof

        return Proof(proof="sorry")

    def _prove_all(self, tactics: list[str]) -> str:
        prove_independent = " ; ".join([f"(all_goals try {t})" for t in tactics])
        prove_combined = "all_goals (" + " ; ".join([f"(try {t})" for t in tactics]) + ")"
        return "all_goals intros; first | (" + prove_independent + ") | (" + prove_combined + ")"
