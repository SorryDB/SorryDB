from pathlib import Path

from sorrydb.agents.json_agent import SorryStrategy
from sorrydb.database.sorry import Proof, Sorry


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
        self.tactics = [
            "rfl",
            "ring",
            "norm_num",
            "simp_all",
            "grind",
            "omega",
            "linarith",
            "nlinarith",
            "aesop",
            "exact?",
            "hint",
        ]

    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> Proof | None:
        return Proof(proof=self._prove_all())

    def _prove_all(self) -> str:
        tactics = self.tactics
        prove_independent = " ; ".join([f"(all_goals try {t})" for t in tactics])
        prove_combined = (
            "all_goals (" + " ; ".join([f"(try {t})" for t in tactics]) + ")"
        )
        return (
            "all_goals intros\nfirst | ("
            + prove_independent
            + ") | ("
            + prove_combined
            + ")"
        )
