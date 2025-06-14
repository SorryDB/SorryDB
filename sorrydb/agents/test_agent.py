import contextlib
import dataclasses
import logging
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from sorrydb.agents.json_agent import SorryStrategy, load_sorry_json, save_proofs_json
from sorrydb.agents.sagemaker_hugging_face_strategy import LLMResponseDebugInfo
from sorrydb.database.sorry import Sorry
from sorrydb.utils.git_ops import prepare_repository

# Create a module-level logger
logger = logging.getLogger(__name__)


class TestAgent:
    def __init__(self, strategy: SorryStrategy, lean_data_path: Path | None = None):
        self.strategy = strategy
        self.lean_data_path = lean_data_path

    def _process_sorries(
        self, local_sorries: list[Sorry], lean_data_dir: Path
    ) -> list[dict]:
        proofs = []
        for sorry in local_sorries:
            try:
                # Prepare the repository (clone and checkout)
                checkout_path = prepare_repository(
                    sorry.repo.remote,
                    sorry.repo.branch,
                    sorry.repo.commit,
                    lean_data_dir,
                )

                # Attempt to prove the sorry
                proof_string, debug_info = self.strategy.prove_sorry(
                    checkout_path, sorry
                )
                logger.debug(f"Strategy produce proof string: {proof_string}")

                proofs.append(
                    {
                        "sorry": sorry,
                        "proof": proof_string,
                        "debug_info": dataclasses.asdict(debug_info),
                    }
                )
            except Exception as e:
                # Continue if an exception is raised when processing a sorry
                logger.error(f"Exception {e} raised while processing sorry: {sorry}")
                proofs.append(
                    {
                        "sorry": sorry,
                        "proof": None,
                        "exception": {"type": type(e).__name__, "message": str(e)},
                    }
                )
        return proofs

    def _process_sorries_wrapper(self, sorries: list[Sorry]) -> list[dict]:
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

        # group sorries by remote url to minimize temporary disk usage
        for remote_url in remote_urls:
            local_sorries = [
                sorry for sorry in sorries if sorry.repo.remote == remote_url
            ]
            proofs.extend(self._process_sorries_wrapper(local_sorries))
            # Incrementally save the proofs as we are processing sorries
            save_proofs_json(proofs_json_path, proofs)

        save_proofs_json(proofs_json_path, proofs)
