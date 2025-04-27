from typing import Protocol
from pathlib import Path
from sorrydb.database.sorry import Sorry
import json



class SorryStrategy(Protocol):
    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str:
        pass

class JsonAgent:
    def __init__(self, strategy: SorryStrategy, lean_data_path: Path | None = None):
        self.strategy = strategy
        self.lean_data_path = lean_data_path

    def _process_repo(self, remote_url: str, local_sorries: list[dict]) -> list[dict]:
        pass

    def process_sorries(self, sorry_json_path: Path, proofs_json_path: Path):
        # load sorries from the json
        sorries = json.load(sorry_json_path.read_text())

        # extract list of unique remote urls
        remote_urls = set(sorry["repo"]["remote_url"] for sorry in sorries)

        proofs = []
        for remote_url in remote_urls:
            # extract list of sorries for this remote url
            local_sorries = [sorry for sorry in sorries if sorry["repo"]["remote_url"] == remote_url]

            proofs.extend(_process_repo(self, remote_url, local_sorries))

        # write proofs to the json
        proofs_json_path.write_text(json.dumps(proofs, indent=2))



