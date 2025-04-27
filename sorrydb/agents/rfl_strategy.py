from sorrydb.agents.json_agent import SorryStrategy
from pathlib import Path
from typing import Dict


class RflStrategy(SorryStrategy):
    def prove_sorry(self, repo_path: Path, sorry: Dict) -> str | None:
        return "rfl"


