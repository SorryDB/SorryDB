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
