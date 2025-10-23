import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from git import Repo

from sorrydb.runners.json_runner import SorryStrategy, load_sorry_json
from sorrydb.database.sorry import Sorry, SorryJSONEncoder
from sorrydb.utils.lean_repo import build_lean_project
from sorrydb.utils.verify import verify_proof

logger = logging.getLogger(__name__)


@dataclass
class LoadedSorry:
    sorry: Sorry
    checkout_path: Path

    def to_dict(self):
        return {
            "sorry": self.sorry,
            "checkout_path": str(self.checkout_path),
        }


class AttemptStatus(str, Enum):
    INIT = "INIT"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    FAILED = "FAILED"
    SUCCESS = "SUCCESS"


@dataclass
class SorryAttempt:
    name: str
    loaded_sorry: LoadedSorry
    proof: Proof | None = None
    attempt_exception: Exception | None = None
    verification_exception: Exception | None = None
    status: AttemptStatus = AttemptStatus.INIT
    strategy_time: float | None = None
    verification_time: float | None = None
    debug_info: dict | None = None


class StrategyComparisonRunner:
    """
    Used to compare SorryStrategy instances

    Also useful because it allows more precise control over when sorries are loaded and verfied.
    This lets you just spin up cloud computing resources for the inference.
    """

    def __init__(self, lean_data_path: Path):
        self.lean_data_path = lean_data_path
        self.loaded_sorries: list[LoadedSorry] = []
        self.sorry_attempts: list[SorryAttempt] = []
        self.strategies: list[SorryStrategy] = []

    def _ensure_repo_is_prepared(
        self,
        remote_url: str,
        commit: str,
        lean_data: Path,
        lean_version: str,
    ) -> Path:
        # Create a directory name from the remote URL
        repo_name = remote_url.rstrip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        checkout_path = lean_data / repo_name / lean_version / commit
        if not checkout_path.exists():
            logger.info(f"Cloning {remote_url}")
            repo = Repo.clone_from(remote_url, checkout_path)
            logger.info(f"Checking out {repo_name} repo at commit {commit}")
            repo.git.checkout(commit)
        else:
            logger.info(
                f"Repo {repo_name} with version {lean_version} on commit {commit} already exists at {checkout_path}"
            )
            repo = Repo(checkout_path)

        return checkout_path

    def load_sorries(self, sorry_json_path: Path, build_lean_projects: bool):
        logger.info("Loading sorries")
        sorries = load_sorry_json(sorry_json_path)
        for sorry in sorries:
            try:
                checkout_path = self._ensure_repo_is_prepared(
                    sorry.repo.remote,
                    sorry.repo.commit,
                    self.lean_data_path,
                    sorry.repo.lean_version,
                )
                self.loaded_sorries.append(LoadedSorry(sorry, checkout_path))
            except Exception as e:
                logger.error(
                    f"Error preparing repository for {sorry.repo.remote}: {e}. Skipping..."
                )
                continue

            try:
                if build_lean_projects:
                    build_lean_project(checkout_path)
            except Exception as e:
                logger.error(
                    f"Error building Lean project for {sorry.repo.remote}: {e}. Skipping..."
                )
                continue

    def attempt_sorries(self, strategy: SorryStrategy, attempt_name: str | None = None):
        # Add strategy to strategies list so it can be included in the report config
        self.strategies.append(strategy)

        if not attempt_name:
            attempt_name = str(strategy)
        logger.info(f"Attempting sorries with attempt: {attempt_name}")

        for n, loaded_sorry in enumerate(self.loaded_sorries):
            logger.info(
                f"Attempting sorry {n}/{len(self.loaded_sorries)} for attempt: {attempt_name}"
            )
            attempt = SorryAttempt(attempt_name, loaded_sorry)
            start_time = time.perf_counter()
            try:
                attempt.proof = strategy.prove_sorry(
                    loaded_sorry.checkout_path, loaded_sorry.sorry
                )
                attempt.status = AttemptStatus.PENDING_VERIFICATION
            except Exception as e:
                attempt.attempt_exception = e
                attempt.status = AttemptStatus.FAILED
            finally:
                end_time = time.perf_counter()
                attempt.strategy_time = end_time - start_time
                attempt.debug_info = strategy.get_debug_info()
            self.sorry_attempts.append(attempt)

    def verify_proofs(self):
        logging.info("Verifying proofs")
        for attempt in self.sorry_attempts:
            if (
                attempt.status == AttemptStatus.PENDING_VERIFICATION
                and attempt.proof
            ):
                logger.info(
                    f"Verifying attempt of {attempt.loaded_sorry.sorry.repo.remote} on {attempt.name}"
                )
                start_time = time.perf_counter()
                try:
                    proof_verified, error_msg = verify_proof(
                        attempt.loaded_sorry.checkout_path,
                        attempt.loaded_sorry.sorry.repo.lean_version,
                        attempt.loaded_sorry.sorry.location,
                        attempt.proof,
                    )
                    if proof_verified:
                        attempt.status = AttemptStatus.SUCCESS
                    else:
                        attempt.status = AttemptStatus.FAILED
                except Exception as e:
                    attempt.verification_exception = e
                finally:
                    end_time = time.perf_counter()
                    attempt.verification_time = end_time - start_time

    def write_report(self, output_path: Path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_directory = output_path / f"run_{timestamp}"
        logger.info(f"Creating report directory {report_directory}")
        os.makedirs(report_directory, exist_ok=True)

        def serialize_exception(exc):
            return str(exc) if exc else None

        report = []
        for attempt in self.sorry_attempts:
            repo_name = attempt.loaded_sorry.sorry.debug_info.url.rstrip("/").split(
                "/"
            )[-1]
            report.append(
                {
                    "attempt_name": attempt.name,
                    "status": attempt.status.value,
                    "proof_string": attempt.proof,
                    "lean_version": attempt.loaded_sorry.sorry.repo.lean_version,
                    "goal": attempt.loaded_sorry.sorry.debug_info.goal,
                    "repo_name": repo_name,
                    "url": attempt.loaded_sorry.sorry.debug_info.url,
                    "checkout_path": str(attempt.loaded_sorry.checkout_path),
                    "attempt_exception": serialize_exception(attempt.attempt_exception),
                    "verification_exception": serialize_exception(
                        attempt.verification_exception
                    ),
                    "strategy_time": attempt.strategy_time,
                    "verification_time": attempt.verification_time,
                    "sorry_id": attempt.loaded_sorry.sorry.id,
                    "debug_info": attempt.debug_info,
                }
            )

        run_config = {
            "strategies": [str(strategy) for strategy in self.strategies],
            "sorries": [loaded_sorry.to_dict() for loaded_sorry in self.loaded_sorries],
        }

        with open(output_path / report_directory / "report.json", "w") as f:
            json.dump(report, f, indent=2, cls=SorryJSONEncoder, ensure_ascii=False)

        with open(output_path / report_directory / "run_config.json", "w") as f:
            json.dump(run_config, f, indent=2, cls=SorryJSONEncoder, ensure_ascii=False)
