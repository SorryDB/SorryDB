from pathlib import Path

from sorrydb.agents.json_agent import SorryStrategy
from sorrydb.database.sorry import Sorry


class RflStrategy(SorryStrategy):
    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str | None:
        return "rfl"
