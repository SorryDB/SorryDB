from sorrydb.agents.json_agent import SorryStrategy
from sorrydb.database.sorry import Sorry
from pathlib import Path
from typing import Dict


class RflStrategy(SorryStrategy):
    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str | None:
        return "rfl"


