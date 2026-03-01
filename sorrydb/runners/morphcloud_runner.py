import asyncio
import json
import os
import re
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable
from collections import defaultdict

from dotenv import find_dotenv, load_dotenv
from git import Repo
import httpx
from morphcloud.api import ApiError, Instance, MorphCloudClient
from paramiko.ssh_exception import SSHException, ChannelException

# Global counter for tracking concurrent builds
_concurrent_builds = 0
_concurrent_builds_lock = asyncio.Lock()

from ..runners.json_runner import load_sorry_json
from ..database.sorry import FailedSorry, RepoInfo, Sorry, SorryJSONEncoder, SorryResult
from ..utils.git_ops import github_commit_exists, parse_remote, sanitize_repo_name
from ..utils.logging import setup_logger

load_dotenv()
MORPH_API_KEY = os.environ["MORPH_API_KEY"]
FINAL_OUTPUT_NAME = "result.json"
FAILED_OUTPUT_NAME = "failed.json"
RUN_SUMMARY_NAME = "run_summary.json"
BUILD_TIMEOUT = 1800  # 30 minutes - timeout for snap.abuild()
MAX_BUILD_RETRIES = 3  # Number of retries on timeout (cached steps are reused)
PROCESS_SORRY_TIMEOUT = 10000  # timeout for instance operations in _process_single_sorry_async
FILE_OP_TIMEOUT = 120  # timeout for quick file operations (aexec for .env, adownload)
POLL_INTERVAL = 60  # seconds between result file checks
POLL_CHECK_TIMEOUT = 30  # timeout for each poll check command


class MathlibCacheError(Exception):
    """Raised when mathlib cache download fails after all retry attempts."""
    pass


def _calculate_sorry_stats(results: list[SorryResult]) -> dict:
    """Calculate stats grouped by unique sorry ID.

    For multi_tactic runs, multiple results can exist per sorry.
    This function calculates both unique sorry counts and total result counts.

    Returns:
        dict with keys:
        - unique_sorries: number of distinct sorries processed
        - unique_verified: number of sorries with at least one verified result
        - unique_failed: number of sorries where all results failed (success=False)
        - total_results: total number of results (tactic attempts)
        - verified_results: number of results with proof_verified=True
    """
    by_sorry = defaultdict(list)
    for r in results:
        # Handle both Sorry object and dict (from JSON deserialization)
        sorry = r.sorry
        if sorry:
            if isinstance(sorry, dict):
                sorry_id = sorry.get("id")
            else:
                sorry_id = sorry.id
            if sorry_id:
                by_sorry[sorry_id].append(r)

    unique_sorries = len(by_sorry)
    unique_verified = sum(1 for sorry_results in by_sorry.values()
                         if any(r.proof_verified for r in sorry_results))
    unique_failed = sum(1 for sorry_results in by_sorry.values()
                       if not any(r.success for r in sorry_results))

    return {
        "unique_sorries": unique_sorries,
        "unique_verified": unique_verified,
        "unique_failed": unique_failed,
        "total_results": len(results),
        "verified_results": sum(1 for r in results if r.proof_verified),
    }


def _create_cache_retry_step() -> Callable[[Instance], None]:
    """Create a callable step for lake exe cache get with retry.

    Only attempts cache download if mathlib4 is detected in lake-manifest.json.
    Raises MathlibCacheError if mathlib is present but cache download fails.
    Logs output to /tmp/step_3b.log on the remote instance.
    """
    def step(instance: Instance) -> None:
        import time

        log = "/tmp/step_3b.log"

        # Check if this is mathlib4 repo itself (or a fork) OR depends on mathlib4
        check_result = instance.exec(
            f'(git -C repo remote get-url origin | grep -q "mathlib4" && '
            f'echo "Mathlib4 repository detected") > {log} 2>&1 || '
            f'(grep -qE "github\\.com/[^/]+/mathlib4" repo/lake-manifest.json && '
            f'echo "Mathlib4 dependency detected") >> {log} 2>&1'
        )
        if check_result.exit_code != 0:
            instance.exec(f'echo "No mathlib4 repository or dependency detected, skipping" >> {log}')
            print("[cache] No mathlib4 repository or dependency detected, skipping cache download")
            return

        print("[cache] Mathlib4 detected (repo or dependency), downloading cache...")

        max_attempts = 5
        base_delay = 5  # seconds

        for attempt in range(1, max_attempts + 1):
            instance.exec(f'echo "Attempt {attempt}/{max_attempts}" >> {log}')
            result = instance.exec(
                f'(cd repo && export PATH="$HOME/.elan/bin:$PATH" && lake exe cache get) >> {log} 2>&1'
            )
            if result.exit_code == 0:
                print(f"[cache] lake exe cache get succeeded on attempt {attempt}")
                return

            print(f"[cache] Attempt {attempt}/{max_attempts} failed (exit_code={result.exit_code})")

            if attempt < max_attempts:
                delay = base_delay * (2 ** (attempt - 1))  # 5, 10, 20, 40
                print(f"[cache] Retrying in {delay}s...")
                time.sleep(delay)

        # Mathlib present but cache failed - this is fatal
        raise MathlibCacheError(
            f"Failed to download mathlib cache after {max_attempts} attempts"
        )

    return step


def _get_log_path(subdirectory: str, filename: str, output_dir: Path | None = None) -> Path:
    if output_dir is not None:
        logs_root = output_dir / "logs" / subdirectory
    else:
        logs_root = Path(__file__).resolve().parents[2] / "logs" / subdirectory
    logs_root.mkdir(parents=True, exist_ok=True)
    return logs_root / filename


def _create_run_summary(
    sorry_json_path: Path,
    strategy_name: str,
    strategy_args: dict,
    max_workers: int,
    start_time: datetime,
    end_time: datetime,
    total_sorries: int,
    prepared_sorries: int,
    failed_builds: int,
    # New parameters for multi_tactic support
    unique_sorries_processed: int,
    unique_sorries_verified: int,
    unique_sorries_failed: int,
    total_results: int,
    verified_results: int,
    results: list = None,  # For cost aggregation
) -> dict:
    """Create a summary dictionary for the run with metadata."""
    # Get SorryDB commit info
    try:
        git_repo = Repo(".")
        sorrydb_branch = git_repo.active_branch.name
        sorrydb_commit = git_repo.head.commit.hexsha
        sorrydb_commit_short = sorrydb_commit[:12]
        sorrydb_commit_message = git_repo.head.commit.message.strip()
        sorrydb_is_dirty = git_repo.is_dirty()
    except Exception as e:
        sorrydb_branch = "unknown"
        sorrydb_commit = "unknown"
        sorrydb_commit_short = "unknown"
        sorrydb_commit_message = f"Error getting commit info: {e}"
        sorrydb_is_dirty = None

    duration_seconds = (end_time - start_time).total_seconds()

    summary = {
        "run_metadata": {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration_seconds,
            "duration_human": f"{int(duration_seconds // 60)}m {int(duration_seconds % 60)}s",
        },
        "sorrydb_info": {
            "branch": sorrydb_branch,
            "commit": sorrydb_commit,
            "commit_short": sorrydb_commit_short,
            "commit_message": sorrydb_commit_message,
            "is_dirty": sorrydb_is_dirty,
        },
        "input": {
            "sorry_json_path": str(sorry_json_path),
            "sorry_json_filename": sorry_json_path.name,
        },
        "strategy": {
            "name": strategy_name,
            "args": strategy_args,
        },
        "execution": {
            "max_workers": max_workers,
        },
        "results": {
            "total_sorries_loaded": total_sorries,
            "prepared_sorries": prepared_sorries,
            "failed_builds": failed_builds,
            # Unique sorry counts (for comparing across strategies)
            "unique_sorries_processed": unique_sorries_processed,
            "unique_sorries_verified": unique_sorries_verified,
            "failed_processing": unique_sorries_failed,
            # Result counts (for multi_tactic visibility)
            "total_results": total_results,
            "verified_results": verified_results,
        },
    }

    # Aggregate costs from results if available
    if results:
        total_input_tokens = sum(getattr(r, 'input_tokens', 0) or 0 for r in results)
        total_output_tokens = sum(getattr(r, 'output_tokens', 0) or 0 for r in results)
        total_cost = sum(getattr(r, 'estimated_cost', 0) or 0 for r in results)

        summary["cost"] = {
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_cost_usd": round(total_cost, 4),
        }

    return summary


async def _poll_for_result_file(
    instance: Instance,
    result_path: str,
    poll_interval: float,
    logger
) -> bool:
    """Poll for result file existence on a MorphCloud instance.

    Args:
        instance: The MorphCloud instance to check
        result_path: Path to the result file on the remote instance
        poll_interval: Seconds between checks
        logger: Logger for debug output

    Returns:
        True when the file is detected
    """
    while True:
        await asyncio.sleep(poll_interval)
        try:
            check = await asyncio.wait_for(
                instance.aexec(f"test -f {result_path} && echo 'exists'", timeout=POLL_CHECK_TIMEOUT),
                timeout=POLL_CHECK_TIMEOUT
            )
            if "exists" in check.stdout:
                logger.info(f"[poll] Result file detected at {result_path}")
                return True
        except (asyncio.TimeoutError, Exception) as e:
            # Log but continue polling - the check itself might hang
            logger.info(f"[poll] Check failed: {e}, continuing...")


async def _process_single_sorry_async(
    mc: MorphCloudClient,
    sorry: Sorry,
    snapshot_id: str,
    strategy_name: str,
    strategy_args: dict,
    output_dir: Path,
    index: int,
    total: int
) -> list[SorryResult]:
    """Async function to process a single sorry on a MorphCloud instance.

    Args:
        mc: Shared MorphCloudClient instance
        sorry: The sorry to process
        snapshot_id: Pre-built snapshot ID to use for this sorry's repository
        strategy_name: Name of the strategy to use
        strategy_args: Arguments for the strategy
        output_dir: Directory to save output files
        index: Current index (1-based) for progress tracking
        total: Total number of sorries being processed
    """
    log_path = _get_log_path("process_single_sorry", f"{sorry.id}.log", output_dir)

    with setup_logger(f"process_sorry_{sorry.id}", log_path) as logger:
        # Console output for progress tracking
        repo_name = sanitize_repo_name(sorry.repo.remote)
        commit_short = sorry.repo.commit[:12] if sorry.repo.commit else "unknown"
        print(f"[{index}/{total}] Starting {sorry.id} ({repo_name}@{commit_short})")

        logger.info(f"[process_single_sorry] Starting for sorry {sorry.id}")
        logger.info(f"[process_single_sorry] Using snapshot: {snapshot_id}")
        logger.info(f"[process_single_sorry] Repository: {sorry.repo.remote}@{sorry.repo.commit}")

        # Create descriptive instance name: {repo_name}_{commit_short}_{strategy}_{sorry_id}
        repo_name = sanitize_repo_name(sorry.repo.remote)
        commit_short = sorry.repo.commit[:12] if sorry.repo.commit else "unknown"
        instance_name = f"{repo_name}_{commit_short}_{strategy_name}_{sorry.id}"
        logger.info(f"[process_single_sorry] Instance name: {instance_name}")

        for attempt in range(1, 5):  # 4 attempts total
            logger.info(f"[process_single_sorry] Starting attempt {attempt}/4")
            try:
                logger.info("[process_single_sorry] Starting instance from snapshot...")
                with await mc.instances.astart(
                    snapshot_id=snapshot_id,
                    ttl_seconds=PROCESS_SORRY_TIMEOUT + 120,
                    timeout=PROCESS_SORRY_TIMEOUT + 60, 
                    metadata={
                        "name": instance_name,
                        "repo": sorry.repo.remote,
                        "commit": sorry.repo.commit,
                        "strategy": strategy_name,
                        "sorry_id": sorry.id
                    }
                ) as instance:
                    logger.info(f"[process_single_sorry] Instance started successfully: {instance.id}")

                    # Create .env file using aexec
                    logger.info("[process_single_sorry] Creating .env file...")
                    with open(find_dotenv(), "r") as f:
                        env_content = f.read()

                    # Handle GOOGLE_APPLICATION_CREDENTIALS - copy the key file to the instance
                    gcp_creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
                    if gcp_creds_path and os.path.exists(gcp_creds_path):
                        logger.info(f"[process_single_sorry] Copying GCP credentials from {gcp_creds_path}...")
                        remote_creds_path = "/root/gcp-sa-key.json"

                        # Use native SFTP upload - reliable for any file size
                        try:
                            await asyncio.wait_for(
                                instance.aupload(gcp_creds_path, remote_creds_path),
                                timeout=FILE_OP_TIMEOUT
                            )
                            logger.info(f"[process_single_sorry] GCP key file uploaded successfully")
                        except asyncio.TimeoutError as e:
                            raise TimeoutError(f"Uploading GCP key file timed out after {FILE_OP_TIMEOUT} seconds") from e
                        except Exception as e:
                            raise RuntimeError(f"Failed to upload GCP key file: {e}") from e

                        # Update the env_content to use the remote path
                        env_content = re.sub(
                            r"GOOGLE_APPLICATION_CREDENTIALS=.*",
                            f"GOOGLE_APPLICATION_CREDENTIALS={remote_creds_path}",
                            env_content
                        )

                    create_env_cmd = f"cat > SorryDB/.env << 'EOF'\n{env_content}\nEOF"
                    try:
                        env_result = await asyncio.wait_for(instance.aexec(create_env_cmd), timeout=FILE_OP_TIMEOUT)
                    except asyncio.TimeoutError as e:
                        raise TimeoutError(f"Creating .env file timed out after {FILE_OP_TIMEOUT} seconds") from e
                    logger.info(f"[process_single_sorry] .env file created (exit_code: {env_result.exit_code})")

                    # Copy aristotle_projects.json if specified for aristotle_collect strategy
                    projects_file_path = strategy_args.get("projects_file")
                    if projects_file_path and os.path.exists(projects_file_path):
                        logger.info(f"[process_single_sorry] Copying projects file from {projects_file_path}...")
                        remote_projects_path = "/root/aristotle_projects.json"

                        # Use native SFTP upload - reliable for any file size
                        try:
                            await asyncio.wait_for(
                                instance.aupload(projects_file_path, remote_projects_path),
                                timeout=FILE_OP_TIMEOUT
                            )
                            logger.info(f"[process_single_sorry] Projects file uploaded successfully")
                        except asyncio.TimeoutError as e:
                            raise TimeoutError(f"Uploading projects file timed out after {FILE_OP_TIMEOUT} seconds") from e
                        except Exception as e:
                            raise RuntimeError(f"Failed to upload projects file: {e}") from e

                        # Update strategy_args to use remote path
                        strategy_args = {**strategy_args, "projects_file": remote_projects_path}

                    # Prepare JSON arguments, escaping single quotes for bash
                    sorry_json = json.dumps(sorry, cls=SorryJSONEncoder).replace("'", "'\"'\"'")
                    strategy_json = json.dumps({"name": strategy_name, "args": strategy_args}).replace("'", "'\"'\"'")

                    cmd = (
                        f"cd SorryDB && "
                        f'export PATH="$HOME/.local/bin:$PATH" && '
                        f'export PATH="$HOME/.elan/bin:$PATH" && '
                        f"poetry run python -m sorrydb.cli.run_morphcloud_local "
                        f"--repo-path ~/repo "
                        f"--sorry-json '{sorry_json}' "
                        f"--agent-strategy '{strategy_json}'"
                    )
                    logger.info("[process_single_sorry] Executing agent command with concurrent polling...")

                    # Create both tasks: main aexec and polling for result file
                    main_task = asyncio.create_task(
                        instance.aexec(cmd, PROCESS_SORRY_TIMEOUT),
                        name="main_aexec"
                    )
                    poll_task = asyncio.create_task(
                        _poll_for_result_file(instance, "/root/repo/result.json", POLL_INTERVAL, logger),
                        name="poll_result"
                    )

                    timeout_error = None  # Store error to raise after downloading logs
                    download_run_log = False  # Track if we need run.log (no stdout available)

                    try:
                        done, pending = await asyncio.wait(
                            [main_task, poll_task],
                            timeout=PROCESS_SORRY_TIMEOUT,
                            return_when=asyncio.FIRST_COMPLETED
                        )

                        # Cancel pending tasks
                        for task in pending:
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass

                        # Determine what happened
                        if main_task in done:
                            # Main task completed (normally or with exception)
                            res = main_task.result()  # May raise if aexec failed
                            logger.info(f"[process_single_sorry] Agent command completed (exit_code: {res.exit_code})")
                            logger.info(f"[process_single_sorry] STDOUT:\n{res.stdout}")
                            if res.stderr:
                                logger.info(f"[process_single_sorry] STDERR:\n{res.stderr}")
                        elif poll_task in done:
                            # Poll detected result file - aexec is hanging but work is done
                            logger.info("[process_single_sorry] Result file detected via polling (aexec still running)")
                            download_run_log = True  # Need run.log since no stdout from hanging aexec
                        else:
                            # Both timed out - store error, don't raise yet
                            timeout_error = TimeoutError(f"Agent command execution timed out after {PROCESS_SORRY_TIMEOUT} seconds")

                    except asyncio.TimeoutError as e:
                        timeout_error = TimeoutError(f"Agent command execution timed out after {PROCESS_SORRY_TIMEOUT} seconds")

                    # Download run.log if stdout unavailable (poll success or timeout)
                    if download_run_log or timeout_error:
                        run_log_path = _get_log_path("remote_morph_logs", f"{sorry.id}_attempt_{attempt}_run.log", output_dir)
                        try:
                            await asyncio.wait_for(
                                instance.adownload("/root/repo/run.log", str(run_log_path)),
                                timeout=FILE_OP_TIMEOUT
                            )
                            logger.info(f"[process_single_sorry] Downloaded run.log to {run_log_path}")
                        except Exception as e:
                            logger.warning(f"[process_single_sorry] Failed to download run.log: {e}")

                    # Raise timeout error after downloading logs
                    if timeout_error:
                        raise timeout_error

                    # Save individual result file for debugging
                    logger.info("[process_single_sorry] Downloading result file...")
                    individual_dir = output_dir / "individual"
                    individual_dir.mkdir(parents=True, exist_ok=True)
                    output_path = individual_dir / f"{sorry.id}.json"
                    try:
                        await asyncio.wait_for(instance.adownload("/root/repo/result.json", str(output_path)), timeout=FILE_OP_TIMEOUT)
                    except asyncio.TimeoutError as e:
                        raise TimeoutError(f"Downloading result file timed out after {FILE_OP_TIMEOUT} seconds") from e
                    logger.info(f"[process_single_sorry] Downloaded result to {output_path}")

                logger.info("[process_single_sorry] Instance context closed successfully")

                # Parse and return the result directly
                logger.info("[process_single_sorry] Parsing result file...")
                with open(output_path, "r") as f:
                    result_data = json.load(f)

                # Handle both dict and list formats - always return list
                if isinstance(result_data, dict):
                    logger.info(f"[process_single_sorry] Successfully parsed result (dict format, 1 result)")
                    print(f"[{index}/{total}] Completed {sorry.id}")
                    return [SorryResult(**result_data)]
                elif isinstance(result_data, list) and len(result_data) > 0:
                    # Return all results from the list
                    logger.info(f"[process_single_sorry] Successfully parsed result (list format, {len(result_data)} results)")
                    print(f"[{index}/{total}] Completed {sorry.id} ({len(result_data)} results)")
                    return [SorryResult(**r) for r in result_data]
                else:
                    logger.error(f"[process_single_sorry] Unexpected result format for {sorry.id}: {type(result_data)}")
                    print(f"[{index}/{total}] Failed {sorry.id}: unexpected format")
                    return [SorryResult(
                        sorry=sorry,
                        proof=None,
                        proof_verified=False,
                        success=False,
                        error_type="unexpected_format",
                        error_message=f"Unexpected result format: {type(result_data)}",
                        feedback=f"Unexpected result format: expected dict or list, got {type(result_data)}"
                    )]

            except (TimeoutError, httpx.NetworkError, ApiError, SSHException, httpx.RemoteProtocolError) as e:
                # Retryable errors: timeouts, network failures, and morphcloud API errors
                logger.error(f"[process_single_sorry] Retryable error on attempt {attempt}/4: {type(e).__name__}: {e}")
                print(f"[{index}/{total}] {type(e).__name__} {sorry.id} (attempt {attempt}/4)")
                if attempt < 4:
                    # Exponential backoff: 5s, 10s, 20s, ...
                    backoff_delay = 5 * (2 ** (attempt - 1))
                    logger.warning(f"[process_single_sorry] Waiting {backoff_delay} seconds before retry (exponential backoff)...")
                    await asyncio.sleep(backoff_delay)
                    continue  # Retry
                else:
                    logger.error(f"[process_single_sorry] All 4 attempts exhausted")
                    print(f"[{index}/{total}] Failed {sorry.id}: {type(e).__name__} (4 attempts)")
                    return [SorryResult(
                        sorry=sorry,
                        proof=None,
                        proof_verified=False,
                        success=False,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        feedback=f"Failed after 4 attempts: {type(e).__name__}: {str(e)}"
                    )]

            except Exception as e:
                # Non-retryable exceptions - fail immediately
                logger.error(f"[process_single_sorry] Non-retryable exception for {sorry.id}: {type(e).__name__}: {e}")
                print(f"[{index}/{total}] Failed {sorry.id}: {type(e).__name__}")
                return [SorryResult(
                    sorry=sorry,
                    proof=None,
                    proof_verified=False,
                    success=False,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    feedback=f"Non-retryable exception: {type(e).__name__}: {str(e)}"
                )]


async def _prepare_repository_async(mc: MorphCloudClient, repo: RepoInfo, output_dir: Path | None = None) -> dict:
    """Async function to prepare a repository snapshot.

    Args:
        mc: Shared MorphCloudClient instance
        repo: Repository information
        output_dir: Optional output directory for logs
    """
    try:
        repo_name = sanitize_repo_name(repo.remote)
        commit_short = (repo.commit or "unknown")[:12]
        log_path = _get_log_path("prepare_repository", f"{repo_name}_{commit_short}.log", output_dir)

        with setup_logger(f"prepare_repo_{repo_name}_{commit_short}", log_path) as logger:
            logger.info(f"[prepare_repository] Starting for {sanitize_repo_name(repo.remote)}")
            logger.info(f"[prepare_repository] Repository details: remote={repo.remote}, commit={repo.commit}")

            # Create descriptive snapshot name: {repo_name}_{commit_short}
            snapshot_name = f"{repo_name}_{commit_short}"
            logger.info(f"[prepare_repository] Snapshot name: {snapshot_name}")

            logger.info("[prepare_repository] Creating snapshot (vcpus=4, memory=16384, disk_size=25000)...")
            try:
                snap = await mc.snapshots.acreate(
                    vcpus=4,
                    memory=16384,
                    disk_size=25000,
                    digest="sorrydb-01-13-26",
                    metadata={
                        "name": snapshot_name,
                        "repo": repo.remote,
                        "commit": repo.commit
                    }
                )
            except Exception as e:
                error_message = f"Exception during creating snapshot: {str(e)}"
                logger.error(f"[prepare_repository] {error_message}")
                logger.error(f"[prepare_repository] Exception type: {type(e).__name__}")
                logger.error(f"[prepare_repository] Exception details: {repr(e)}")
                return {
                    "snapshot_id": None,
                    "remote": repo.remote,
                    "commit": repo.commit,
                    "stdout": "",
                    "stderr": "",
                    "error_message": error_message,
                }

            logger.info(f"[prepare_repository] Snapshot created: {snap.id}")

            # Resolve the latest commit on the current branch to pin the build reproducibly
            try:
                git_repo = Repo(".")
                sorrydb_branch_ref = git_repo.active_branch.name
                sorrydb_commit_ref = git_repo.head.commit.hexsha
                logger.info(f"[prepare_repository] Using current branch {sorrydb_branch_ref} at commit {sorrydb_commit_ref}")
            except Exception as e:
                # Fallback if we can't determine branch/commit (e.g., detached HEAD)
                sorrydb_branch_ref = "unknown"
                sorrydb_commit_ref = "unknown"
                logger.info(f"[prepare_repository] Warning: could not resolve branch/commit: {e}")

            steps = [
                # Step 1: Install system dependencies and toolchain
                (
                    "("
                    "apt-get update && "
                    "apt-get install -y curl git wget htop gnupg python3 python3-pip python3-venv python-is-python3 pipx python3-dev && "
                    "curl https://elan.lean-lang.org/elan-init.sh -sSf | sh -s -- -y --default-toolchain leanprover/lean4:v4.21.0 && "
                    "pipx install poetry"
                    ") > /tmp/step_1.log 2>&1"
                ),
                # Step 2: Clone and setup SorryDB
                (
                    "("
                    "git clone https://github.com/SorryDB/SorryDB.git && "
                    "cd SorryDB && "
                    f"git checkout 7e6991be03405cfb334a91a67b63a2e1ee550fbe && "  # commit with frozen package deps
                    'export PATH="$HOME/.local/bin:$PATH" && '
                    "poetry install"
                    ") > /tmp/step_2.log 2>&1"
                ),
                # Step 3a: Clone and checkout target repository
                (
                    "("
                    f"git clone {repo.remote} repo && "
                    f"cd repo && "
                    f"git fetch origin {repo.commit} && "
                    f"git checkout {repo.commit}"
                    ") > /tmp/step_3a.log 2>&1"
                ),
                # Step 3b: Get lake cache with retry (callable)
                _create_cache_retry_step(),
                # Step 3c: Build the repository
                (
                    "("
                    f"cd repo && "
                    f'export PATH="$HOME/.elan/bin:$PATH" && '
                    f"lake build"
                    ") > /tmp/step_3c.log 2>&1"
                ),
                # Step 4: Finalize SorryDB
                (
                    "("
                    f"cd SorryDB && "
                    f'export PATH="$HOME/.local/bin:$PATH" && '
                    f'export PATH="$HOME/.elan/bin:$PATH" && '
                    f"git fetch && "
                    f"git checkout {sorrydb_commit_ref} && "  # checkout this specific commit
                    f"poetry install && "
                    f"eval $(poetry env activate)"
                    ") > /tmp/step_4.log 2>&1"
                ),
            ]

            logger.info("[prepare_repository] Running build steps...")
            logger.info(f"[prepare_repository] Total build steps: {len(steps)}")
            for i, step in enumerate(steps, 1):
                if isinstance(step, str):
                    logger.info(f"[prepare_repository] Step {i}: {step[:100]}...")
                else:
                    logger.info(f"[prepare_repository] Step {i}: <callable {step.__name__}>")  # Callable step

            error_message = None
            global _concurrent_builds

            try:
                # Track concurrent builds
                async with _concurrent_builds_lock:
                    _concurrent_builds += 1
                    current_concurrent = _concurrent_builds

                build_start_time = time.time()
                logger.info(f"[prepare_repository] Starting abuild call... (concurrent builds: {current_concurrent})")
                logger.info(f"[prepare_repository] Snapshot ID: {snap.id}")

                # Retry loop with timeout for abuild
                snapshot_id = None
                for build_attempt in range(1, MAX_BUILD_RETRIES + 1):
                    try:
                        logger.info(f"[prepare_repository] Build attempt {build_attempt}/{MAX_BUILD_RETRIES}")
                        result = await asyncio.wait_for(
                            snap.abuild(steps=steps),  # type: ignore
                            timeout=BUILD_TIMEOUT
                        )
                        # Success
                        build_duration = time.time() - build_start_time
                        snapshot_id = result.id
                        logger.info(f"[prepare_repository] Build finished successfully: {snapshot_id} (duration: {build_duration:.1f}s)")
                        break

                    except asyncio.TimeoutError:
                        build_duration = time.time() - build_start_time
                        logger.warning(f"[prepare_repository] Build timed out after {BUILD_TIMEOUT}s (attempt {build_attempt}/{MAX_BUILD_RETRIES}, total duration: {build_duration:.1f}s)")
                        if build_attempt == MAX_BUILD_RETRIES:
                            error_message = f"Build timed out after {BUILD_TIMEOUT}s ({MAX_BUILD_RETRIES} attempts, total: {build_duration:.1f}s)"
                            logger.error(f"[prepare_repository] {error_message}")
                        else:
                            logger.info("[prepare_repository] Retrying - cached steps will be reused automatically")
                        # Continue to next attempt (or exit loop if max retries reached)

            except ChannelException as e:
                build_duration = time.time() - build_start_time
                snapshot_id = None
                error_message = f"SSH ChannelException after {build_duration:.1f}s: {str(e)}"
                logger.error(f"[prepare_repository] {error_message}")
                logger.error(f"[prepare_repository] ChannelException code: {e.args[0] if e.args else 'unknown'}")
                logger.error(f"[prepare_repository] ChannelException message: {e.args[1] if len(e.args) > 1 else 'unknown'}")
                logger.error(f"[prepare_repository] Concurrent builds at failure: {current_concurrent}")
                logger.error(f"[prepare_repository] Full traceback:\n{traceback.format_exc()}")

            except SSHException as e:
                build_duration = time.time() - build_start_time
                snapshot_id = None
                error_message = f"SSH Exception after {build_duration:.1f}s: {str(e)}"
                logger.error(f"[prepare_repository] {error_message}")
                logger.error(f"[prepare_repository] SSHException type: {type(e).__name__}")
                logger.error(f"[prepare_repository] Concurrent builds at failure: {current_concurrent}")
                logger.error(f"[prepare_repository] Full traceback:\n{traceback.format_exc()}")

            except Exception as e:
                build_duration = time.time() - build_start_time
                snapshot_id = None
                error_message = f"Exception during build after {build_duration:.1f}s: {str(e)}"
                logger.error(f"[prepare_repository] {error_message}")
                logger.error(f"[prepare_repository] Exception type: {type(e).__name__}")
                logger.error(f"[prepare_repository] Exception details: {repr(e)}")
                logger.error(f"[prepare_repository] Concurrent builds at failure: {current_concurrent}")
                logger.error(f"[prepare_repository] Full traceback:\n{traceback.format_exc()}")
                logger.info("NOTE: Make sure to have pushed your latest commit.")

            finally:
                async with _concurrent_builds_lock:
                    _concurrent_builds -= 1
                    logger.info(f"[prepare_repository] Build ended. Remaining concurrent builds: {_concurrent_builds}")

            return {
                "snapshot_id": snapshot_id,
                "remote": repo.remote,
                "commit": repo.commit,
                "stdout": "",
                "stderr": "",
                "error_message": error_message,
            }
    except Exception as e:
        error_message = f"Exception during preparation: {str(e)}"
        return {
            "snapshot_id": None,
            "remote": repo.remote,
            "commit": repo.commit,
            "stdout": "",
            "stderr": "",
            "error_message": error_message,
        }


def _filter_failed_sorries(sorries: list[Sorry], filter_path: Path) -> list[Sorry]:
    """Filter out sorries that are in filter.json (failed.json)."""
    if not filter_path.exists():
        return sorries

    with open(filter_path, "r") as f:
        filter_data = json.load(f)
        # Extract IDs from FailedSorry objects
        filtered_ids = {item["sorry"]["id"] for item in filter_data}

    filtered = []
    for s in sorries:
        if s.id in filtered_ids:
            print(f"Warning: Skipping sorry {s.id} (found in filter.json)")
        else:
            filtered.append(s)
    return filtered


def _validate_github_commits(sorries: list[Sorry]) -> list[Sorry]:
    """Validate GitHub commits and filter out invalid ones."""
    valid_cache: dict[tuple[str, str], tuple[bool, str]] = {}
    for s in sorries:
        pair = (s.repo.remote, s.repo.commit)
        if pair in valid_cache:
            continue
        host, owner, repo = parse_remote(s.repo.remote)
        if host == "github.com" and owner and repo:
            ok, reason = github_commit_exists(owner, repo, s.repo.commit)
        else:
            ok, reason = True, "skipped-non-github"
        valid_cache[pair] = (ok, reason)

    filtered: list[Sorry] = []
    for s in sorries:
        ok, reason = valid_cache[(s.repo.remote, s.repo.commit)]
        if not ok:
            print(f"[validate_commits] Skipping invalid repo/commit: {s.repo.remote}@{s.repo.commit} -> {reason}")
            continue
        filtered.append(s)
    return filtered


class MorphCloudAgent:
    """
    MorphCloudAgent runs a SorryStrategy on remote MorphCloud instances.

    Similar to JsonRunner but executes on cloud infrastructure:
    - Prepares repositories as snapshots on MorphCloud
    - Spawns instances from snapshots in parallel
    - Runs strategies remotely and downloads results

    Args:
        strategy_name: Name of the strategy to use (e.g., "rfl", "agentic")
        strategy_args: Arguments to pass to the strategy
        max_workers: Maximum number of concurrent workers for both repository preparation and instance execution
    """

    def __init__(
        self,
        strategy_name: str = "rfl",
        strategy_args: dict | None = None,
        max_workers: int = 4,
    ):
        self.strategy_name = strategy_name
        self.strategy_args = strategy_args or {}
        self.max_workers = max_workers

    async def _prepare_sorries(self, sorry_list: list[Sorry], output_dir: Path) -> tuple[list[Sorry], list[FailedSorry], dict[tuple[str, str], str]]:
        """Prepare repository snapshots using async concurrent execution with semaphore.

        Returns:
            tuple: (prepared_sorries, failed_sorries, snapshot_mapping)
                - prepared_sorries: list of sorries with successful repo builds
                - failed_sorries: list of FailedSorry objects with failure information
                - snapshot_mapping: dict mapping (remote, commit) -> snapshot_id
        """
        print(f"[_prepare_sorries] Starting preparation for {len(sorry_list)} sorries")

        # Get unique (remote, commit) pairs
        remote_commit_pairs = {(s.repo.remote, s.repo.commit): s.repo for s in sorry_list}
        repos = list(remote_commit_pairs.values())
        print(f"[_prepare_sorries] Found {len(repos)} unique repositories to build")

        # Create shared MorphCloud client for all preparation tasks
        mc = MorphCloudClient(api_key=MORPH_API_KEY)
        print(f"[_prepare_sorries] Created shared MorphCloudClient instance")

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_workers)

        async def prepare_with_limit(repo: RepoInfo):
            async with semaphore:
                return await _prepare_repository_async(mc, repo, output_dir)

        # Prepare all repositories concurrently with max_workers limit
        print(f"[_prepare_sorries] Starting concurrent builds with max_workers={self.max_workers}")
        tasks = [prepare_with_limit(repo) for repo in repos]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        print(f"[_prepare_sorries] All build tasks completed")

        # Build snapshot mapping and separate sorries
        snapshot_mapping: dict[tuple[str, str], str] = {}
        prepared_sorries = []
        failed_sorries = []

        for idx, result in enumerate(results):
            print(f"[_prepare_sorries] Processing result {idx + 1}/{len(results)}")
            if isinstance(result, Exception):
                # Handle exception case - create FailedSorry for all sorries from unknown repo
                print(f"[prepare_sorries] Exception during preparation: {result}")
                continue

            repo_key = (result["remote"], result["commit"])
            print(f"[_prepare_sorries] Result for {result['remote'][:50]}@{result['commit'][:12]}")

            if result["snapshot_id"] is not None:
                # Cache the snapshot ID
                snapshot_mapping[repo_key] = result["snapshot_id"]
                print(f"[_prepare_sorries] Build successful, snapshot_id={result['snapshot_id']}")
                # Add all sorries from this repo to prepared list
                sorries_for_repo = 0
                for s in sorry_list:
                    if s.repo.remote == result["remote"] and s.repo.commit == result["commit"]:
                        prepared_sorries.append(s)
                        sorries_for_repo += 1
                print(f"[_prepare_sorries] Added {sorries_for_repo} sorries to prepared list")
            else:
                # Create FailedSorry objects for all sorries from this repo
                error_msg = result.get("error_message", "Unknown build failure")
                print(f"[_prepare_sorries] Build failed: {error_msg}")
                sorries_for_repo = 0
                for s in sorry_list:
                    if s.repo.remote == result["remote"] and s.repo.commit == result["commit"]:
                        failed_sorry = FailedSorry(
                            sorry=s,
                            failure_reason=error_msg,
                            failure_type="build_failure"
                        )
                        failed_sorries.append(failed_sorry)
                        sorries_for_repo += 1
                print(f"[_prepare_sorries] Added {sorries_for_repo} sorries to failed list")

        print(f"[_prepare_sorries] Summary: {len(prepared_sorries)} prepared, {len(failed_sorries)} failed, {len(snapshot_mapping)} snapshots")
        return prepared_sorries, failed_sorries, snapshot_mapping

    async def _process_sorries(self, sorries: list[Sorry], snapshot_mapping: dict[tuple[str, str], str], output_dir: Path) -> list[SorryResult]:
        """Process multiple sorries concurrently using async with semaphore.

        Args:
            sorries: List of sorries to process
            snapshot_mapping: Dictionary mapping (remote, commit) -> snapshot_id
            output_dir: Directory to save output files

        Returns:
            List of SorryResult objects (both successful and failed)
        """
        print(f"[_process_sorries] Starting processing for {len(sorries)} sorries")
        print(f"[_process_sorries] Using {len(snapshot_mapping)} cached snapshots")

        # Create shared MorphCloud client for all processing tasks
        mc = MorphCloudClient(api_key=MORPH_API_KEY)
        print(f"[_process_sorries] Created shared MorphCloudClient instance")

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_workers)

        async def process_with_limit(sorry: Sorry, index: int, total: int):
            # Get the snapshot ID for this sorry's repository
            repo_key = (sorry.repo.remote, sorry.repo.commit)
            snapshot_id = snapshot_mapping[repo_key]
            async with semaphore:
                return await _process_single_sorry_async(mc, sorry, snapshot_id, self.strategy_name, self.strategy_args, output_dir, index, total)

        # Process all sorries concurrently with max_workers limit
        print(f"[_process_sorries] Starting concurrent processing with max_workers={self.max_workers}")
        tasks = [process_with_limit(sorry, idx + 1, len(sorries)) for idx, sorry in enumerate(sorries)]
        nested_results = await asyncio.gather(*tasks)
        print(f"[_process_sorries] All processing tasks completed")

        # Flatten nested results (each sorry can produce multiple results with multi_tactic)
        results = [r for sublist in nested_results for r in sublist]

        # Count results (note: for multi_tactic, len(results) > len(sorries))
        successful_count = sum(1 for r in results if r.success)
        failed_count = len(results) - successful_count
        verified_count = sum(1 for r in results if r.proof_verified)
        print(f"[_process_sorries] Summary: {len(sorries)} sorries → {len(results)} results")
        print(f"[_process_sorries] Results: {successful_count} successful, {failed_count} failed, {verified_count} verified")

        return results

    async def process_sorries(self, sorry_json_path: Path, output_dir: Path, filter_dir: Path):
        """Process sorries from a JSON file and save results to output directory.

        Sorries whose repos fail to build are logged in FAILED_OUTPUT_NAME (failed.json)
        in both the output directory and filter directory. To avoid retrying failed sorries,
        the filter_dir is checked for existing failed.json.

        Args:
            sorry_json_path: Path to JSON file containing sorries
            output_dir: Directory to save results (timestamped folder)
            filter_dir: Directory to look for failed.json (base output directory)
        """
        # Track run timing
        start_time = datetime.now()
        print(f"[process_sorries] Run started at {start_time.isoformat()}")

        # Load sorries
        print(f"[process_sorries] Loading sorries from {sorry_json_path}")
        sorries = load_sorry_json(sorry_json_path)
        total_sorries_loaded = len(sorries)
        print(f"[process_sorries] Loaded {total_sorries_loaded} sorries from {sorry_json_path}")

        # Filter out sorries in FAILED_OUTPUT_NAME from the filter directory
        filter_path = filter_dir / FAILED_OUTPUT_NAME
        print(f"[process_sorries] Checking filter file: {filter_path}")
        sorries = _filter_failed_sorries(sorries, filter_path)
        print(f"[process_sorries] After filtering: {len(sorries)} sorries remaining")

        # Validate GitHub commits
        # print(f"[process_sorries] Validating GitHub commits...")
        # sorries = _validate_github_commits(sorries)
        # print(f"[process_sorries] After validation: {len(sorries)} sorries")

        # Prepare repository snapshots
        print("Preparing repository snapshots...")
        sorries, build_failed_sorries, snapshot_mapping = await self._prepare_sorries(sorries, output_dir)
        print(f"Prepared {len(sorries)} sorries with {len(snapshot_mapping)} unique snapshots")

        # Save failed sorries from build stage
        if build_failed_sorries:
            print(f"Failed to build {len(build_failed_sorries)} sorries")
            # Save to timestamped output directory
            failed_path_output = output_dir / FAILED_OUTPUT_NAME
            with open(failed_path_output, "w", encoding="utf-8") as f:
                json.dump(build_failed_sorries, f, indent=4, cls=SorryJSONEncoder, ensure_ascii=False)
            print(f"Failed sorries saved to {failed_path_output}")

            # Merge with existing failures in filter directory
            failed_path_filter = filter_dir / FAILED_OUTPUT_NAME
            existing_failed = []
            if failed_path_filter.exists():
                with open(failed_path_filter, "r") as f:
                    existing_failed = json.load(f)

            # Merge by ID to avoid duplicates
            existing_ids = {item["sorry"]["id"] for item in existing_failed}
            new_failures = [s for s in build_failed_sorries if s.sorry.id not in existing_ids]
            all_failed = existing_failed + new_failures

            with open(failed_path_filter, "w", encoding="utf-8") as f:
                json.dump(all_failed, f, indent=4, cls=SorryJSONEncoder, ensure_ascii=False)
            print(f"Merged {len(new_failures)} new failures into {failed_path_filter} (total: {len(all_failed)})")

        # Process sorries
        print("Processing sorries on MorphCloud...")
        results = await self._process_sorries(sorries, snapshot_mapping, output_dir)

        # Calculate stats (handles both single-strategy and multi_tactic)
        stats = _calculate_sorry_stats(results)

        # Log results with correct terminology (sorries vs results)
        print(f"Successfully processed {stats['unique_sorries']} sorries ({stats['total_results']} results)")
        if stats['unique_failed'] > 0:
            print(f"Failed processing {stats['unique_failed']} sorries (errors captured in results.json)")

        # Write ALL results (both successful and failed) to results.json
        result_path = output_dir / FINAL_OUTPUT_NAME
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4, cls=SorryJSONEncoder, ensure_ascii=False)
        print(f"Results saved to {result_path}")

        # Create and save run summary
        end_time = datetime.now()
        print(f"[process_sorries] Run ended at {end_time.isoformat()}")
        print(f"[process_sorries] {stats['unique_verified']} sorries verified ({stats['verified_results']} verified results)")

        run_summary = _create_run_summary(
            sorry_json_path=sorry_json_path,
            strategy_name=self.strategy_name,
            strategy_args=self.strategy_args,
            max_workers=self.max_workers,
            start_time=start_time,
            end_time=end_time,
            total_sorries=total_sorries_loaded,
            prepared_sorries=len(sorries),
            failed_builds=len(build_failed_sorries),
            unique_sorries_processed=stats['unique_sorries'],
            unique_sorries_verified=stats['unique_verified'],
            unique_sorries_failed=stats['unique_failed'],
            total_results=stats['total_results'],
            verified_results=stats['verified_results'],
            results=results,  # For cost aggregation
        )

        summary_path = output_dir / RUN_SUMMARY_NAME
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(run_summary, f, indent=4, ensure_ascii=False)
        print(f"[process_sorries] Run summary saved to {summary_path}")

        # Finish
        print(f"Results saved to {output_dir}")
        return results


if __name__ == "__main__":
    # Example usage
    async def main():
        agent = MorphCloudAgent(strategy_name="rfl", strategy_args={}, max_workers=4)

        # Process from local file
        sorry_file = Path("mock_sorry.json")
        output_dir = Path("outputs")
        filter_dir = Path("outputs")
        await agent.process_sorries(sorry_file, output_dir, filter_dir)

    asyncio.run(main())
