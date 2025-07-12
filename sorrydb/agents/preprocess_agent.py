import json
import logging
from collections import namedtuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from sorrydb.agents.json_agent import SorryStrategy, load_sorry_json
from sorrydb.database.sorry import Sorry, SorryJSONEncoder
from sorrydb.utils.git_ops import prepare_repository
from sorrydb.utils.verify import verify_proof

logger = logging.getLogger(__name__)


# TODO: remove sorry data from these and use an id?
LoadedSorry = namedtuple("LoadedSorry", ["sorry", "checkout_path"])


class AttemptStatus(str, Enum):
    INIT = "INIT"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    FAILED = "FAILED"
    SUCCESS = "SUCCESS"


@dataclass
class SorryAttempt:
    name: str
    loaded_sorry: LoadedSorry
    proof_string: str | None = None
    attempt_exception: Exception | None = None
    verification_exception: Exception | None = None
    status: AttemptStatus = AttemptStatus.INIT


@dataclass
class ProvedSorry:
    sorry: Sorry
    excpeption: Exception | None = None


class PreprocessAgent:
    def __init__(self, lean_data_path: Path):
        self.lean_data_path = lean_data_path
        self.loaded_sorries: list[LoadedSorry] = []
        self.sorry_attempts: list[SorryAttempt] = []

    def load_sorries(self, sorry_json_path: Path):
        logger.info("Loading sorries")
        sorries = load_sorry_json(sorry_json_path)
        for sorry in sorries:
            # Prepare the repository (clone and checkout)
            try:
                checkout_path = prepare_repository(
                    sorry.repo.remote,
                    sorry.repo.branch,
                    sorry.repo.commit,
                    self.lean_data_path,
                    sorry.repo.lean_version,
                )
                self.loaded_sorries.append(LoadedSorry(sorry, checkout_path))
            except Exception as e:
                logger.error(
                    f"Error preparing repository for {sorry.repo.remote}: {e}. Skipping..."
                )
                raise e

    def attempt_sorries(self, strategy: SorryStrategy, attempt_name: str | None = None):
        if not attempt_name:
            attempt_name = strategy.name()
        logger.info(f"Attempting sorries with attempt: {attempt_name}")

        for loaded_sorry in self.loaded_sorries:
            attempt = SorryAttempt(attempt_name, loaded_sorry)
            try:
                attempt.proof_string = strategy.prove_sorry(
                    loaded_sorry.checkout_path, loaded_sorry.sorry
                )
                attempt.status = AttemptStatus.PENDING_VERIFICATION
            except Exception as e:
                attempt.attempt_exception = e
                attempt.status = AttemptStatus.FAILED
            self.sorry_attempts.append(attempt)

    def verify_proofs(self):
        logging.info("Verifying proofs")
        for attempt in self.sorry_attempts:
            # Only verify the attempt if it is pending verification and has a proof string
            if (
                attempt.status == AttemptStatus.PENDING_VERIFICATION
                and attempt.proof_string
            ):
                try:
                    proof_verified = verify_proof(
                        attempt.loaded_sorry.checkout_path,
                        attempt.loaded_sorry.sorry.repo.lean_version,
                        attempt.loaded_sorry.sorry.location,
                        attempt.proof_string,
                    )
                    if proof_verified:
                        attempt.status = AttemptStatus.SUCCESS
                    else:
                        attempt.status = AttemptStatus.FAILED
                except Exception as e:
                    attempt.verification_exception = e

    def write_report(self, output_path: Path):
        def serialize_exception(exc):
            return str(exc) if exc else None

        report = []
        for attempt in self.sorry_attempts:
            report.append(
                {
                    "name": attempt.name,
                    "status": attempt.status.value,
                    "proof_string": attempt.proof_string,
                    "attempt_exception": serialize_exception(attempt.attempt_exception),
                    "verification_exception": serialize_exception(
                        attempt.verification_exception
                    ),
                    "loaded_sorry": {
                        "sorry": attempt.loaded_sorry.sorry,
                        "checkout_path": str(attempt.loaded_sorry.checkout_path),
                    },
                }
            )
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, cls=SorryJSONEncoder, ensure_ascii=False)
