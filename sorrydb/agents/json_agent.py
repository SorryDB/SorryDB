import contextlib
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, List, Protocol

from sorrydb.database.process_sorries import build_lean_project
from sorrydb.database.sorry import Proof, Sorry, SorryJSONEncoder, SorryResult, sorry_object_hook
from sorrydb.utils.git_ops import prepare_repository
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


def save_sorry_json(output_path: Path, sorries: List[Sorry]):
    """Save a list of sorries to a JSON file.

    Args:
        output_path: Path to output JSON file
        sorries: List of Sorry objects to save
    """
    try:
        with open(output_path, "w") as f:
            json.dump({"sorries": sorries}, f, indent=4, cls=SorryJSONEncoder)
        logger.info(f"Saved {len(sorries)} sorries to {output_path}")
    except Exception as e:
        logger.error(f"Error saving sorries to {output_path}: {e}")
        raise


def save_proofs_json(output_path: Path, output: List[SorryResult]):
    """Save the proofs to a JSON file.

    Args:
        output_path: Path to output JSON file
        output: list of SorryResult objects
    """
    try:
        with open(output_path, "w") as f:
            json.dump(output, f, indent=4, cls=SorryJSONEncoder)
    except Exception as e:
        logger.error(f"Error saving proofs to {output_path}: {e}")
        raise


class SorryStrategy(Protocol):
    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> Proof | None:
        """To be implemented by the agent
        Args:
            repo_path: Path to the repository
            sorry: sorry to prove

        Returns:
            Proof object containing the proof string and optional extra imports, or None if no proof was found
        """
        pass

    def name(self):
        """
        A name to identify the strategy. Used by agents to log and generate reports
        """
        return self.__class__.__name__

    def get_debug_info(self):
        return None


class JsonAgent:
    """
    JsonAgent runs a SorryStrategy on lists of sorries provided via a JSON file.


    Args:
        strategy: The SorryStrategy to use
        lean_data: Path to a directory to store lean data (if None use a temporary directory)
        no_verify: Do not build the lean project or verify the results of the sorry strategy, useful for debugging
    """

    def __init__(
        self,
        strategy: SorryStrategy,
        lean_data_path: Path | None = None,
        no_verify: bool = False,
    ):
        self.strategy = strategy
        self.lean_data_path = lean_data_path
        self.no_verify = no_verify

    def _process_sorries(
        self, local_sorries: list[Sorry], lean_data_dir: Path
    ) -> list[SorryResult]:
        results = []
        for sorry in local_sorries:
            # Prepare the repository (clone and checkout)
            try:
                checkout_path = prepare_repository(
                    sorry.repo.remote,
                    sorry.repo.branch,
                    sorry.repo.commit,
                    lean_data_dir,
                    sorry.repo.lean_version,
                )
            except Exception as e:
                logger.error(
                    f"Error preparing repository for {sorry.repo.remote}: {e}. Skipping..."
                )
                results.append(
                    SorryResult(
                        sorry=sorry,
                        proof=None,
                        proof_verified=False,
                        feedback=f"Repository preparation error: {type(e).__name__}: {str(e)}",
                    )
                )
                continue

            # Build the Lean project
            try:
                if not self.no_verify:
                    build_lean_project(checkout_path)
            except Exception as e:
                logger.error(
                    f"Error building Lean project for {sorry.repo.remote}: {e}. Skipping..."
                )
                results.append(
                    SorryResult(
                        sorry=sorry,
                        proof=None,
                        proof_verified=False,
                        feedback=f"Build error: {type(e).__name__}: {str(e)}",
                    )
                )
                continue

            try:
                # Attempt to prove the sorry
                proof_result = self.strategy.prove_sorry(checkout_path, sorry)

                # Verify the proof
                proof_verified = False
                if not self.no_verify and proof_result is not None:
                    proof_verified, _ = verify_proof(
                        checkout_path,
                        sorry.repo.lean_version,
                        sorry.location,
                        proof_result,
                    )

                # Return SorryResult object
                results.append(
                    SorryResult(
                        sorry=sorry,
                        proof=proof_result,
                        proof_verified=proof_verified,
                        feedback=None,
                    )
                )
            except Exception as e:
                # Continue if an exception is raised when processing a sorry
                logger.error(f"Exception {e} raised while proving sorry: {sorry}")
                results.append(
                    SorryResult(
                        sorry=sorry,
                        proof=None,
                        proof_verified=False,
                        feedback=f"Exception during proof: {type(e).__name__}: {str(e)}",
                    )
                )

        return results

    def _process_sorries_wrapper(self, sorries: list[Sorry]) -> list[SorryResult]:
        with (
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
        idx = 1
        # group sorries by remote url to minimize temporary disk usage
        # sort remotes for consistent processing order
        for remote_url in sorted(remote_urls):
            print(f"Processing proof #{idx}/{len(sorries)}")
            local_sorries = [
                sorry for sorry in sorries if sorry.repo.remote == remote_url
            ]
            proofs.extend(self._process_sorries_wrapper(local_sorries))
            # Incrementally save the proofs as we are processing sorries
            save_proofs_json(proofs_json_path, proofs)
            idx +=len(local_sorries)
        save_proofs_json(proofs_json_path, proofs)
