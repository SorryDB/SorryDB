from typing import Protocol, List, Dict
from pathlib import Path
from sorrydb.database.sorry import Sorry, sorry_object_hook, SorryJSONEncoder
from tempfile import TemporaryDirectory
import json
import logging
import contextlib

from sorrydb.database.process_sorries import build_lean_project
from sorrydb.utils.git_ops import prepare_repository
from sorrydb.utils.lean_repo import build_lean_project
from sorrydb.utils.verify import verify_proof

# Create a module-level logger
logger = logging.getLogger(__name__)


def load_sorry_json(json_path: Path) -> List[Sorry]:
    """Load a sorry JSON file.

    Args:
        json_path: Path to the sorry JSON file

    Returns:
        List of sorries

    Raises:
        FileNotFoundError: If the JSON file doesn't exist
        json.JSONDecodeError: If the JSON file is invalid
    """
    logger.info(f"Loading sorry JSON from {json_path}")
    try:
        with open(json_path, "r") as f:
            sorry_data = json.load(f, object_hook=sorry_object_hook)

        return sorry_data["sorries"]
    except FileNotFoundError:
        logger.error(f"Sorry JSON file not found: {json_path}")
        raise
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in sorry file: {json_path}")
        raise


def save_proofs_json(output_path: Path, output: List[Dict]):
    """Save the proofs to a JSON file.

    Args:
        output_path: Path to output JSON file
        output: list of dicts with sorries and proofs
    """
    try:
        with open(output_path, "w") as f:
            json.dump(output, f, indent=4, cls=SorryJSONEncoder)
    except Exception as e:
        logger.error(f"Error saving proofs to {output_path}: {e}")
        raise


class SorryStrategy(Protocol):
    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str | None:
        """ To be implemented by the agent
        Args:
            repo_path: Path to the repository
            sorry: sorry to prove

        Returns:
            Proof string to replace "sorry" or None if no proof was found
        """
        pass

class JsonAgent:
    def __init__(self, strategy: SorryStrategy, lean_data_path: Path | None = None):
        self.strategy = strategy
        self.lean_data_path = lean_data_path

    def _process_sorries(self, local_sorries: list[Sorry], lean_data_dir: Path) -> list[dict]:
        proofs = []
        for sorry in local_sorries:
            # Prepare the repository (clone and checkout)
            checkout_path = prepare_repository(
                sorry.repo.remote,
                sorry.repo.branch,
                sorry.repo.commit,
                lean_data_dir,
            )

            # Build the Lean project
            build_lean_project(checkout_path)

            # Attempt to prove the sorry
            proof_string = self.strategy.prove_sorry(checkout_path, sorry)

            # Verify the proof
            proof_verified = False
            if proof_string is not None:
                proof_verified = verify_proof(
                    checkout_path,
                    sorry.repo.lean_version,
                    sorry.location,
                    proof_string,
                )

            # Return pair of sorry and proof
            if proof_verified:
                proofs.append({"sorry": sorry, "proof": proof_string})
            else:
                proofs.append({"sorry": sorry, "proof": None})
        return proofs
    
    def _process_sorries_wrapper(self, sorries: list[Sorry]) -> list[dict]:
        with(
            contextlib.nullcontext(self.lean_data_path)
            if self.lean_data_path
            else TemporaryDirectory()
        ) as data_dir:
            lean_data_path = Path(data_dir)
            return self._process_sorries(sorries, lean_data_path)
        
    def process_sorries(self, sorry_json_path: Path, proofs_json_path: Path):
        sorries = load_sorry_json(sorry_json_path)
        remote_urls = set(sorry.repo.remote for sorry in sorries)
        proofs = []

        # group sorries by remote url to minimize temporary disk usage
        for remote_url in remote_urls:
            local_sorries = [sorry for sorry in sorries if sorry.repo.remote == remote_url]
            proofs.extend(self._process_sorries_wrapper(local_sorries))

        save_proofs_json(proofs_json_path, proofs)



