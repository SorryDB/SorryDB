#!/usr/bin/env python3
"""
Run replay verification on MorphCloud instances.

This script re-runs proof extraction and verification using pre-stored LLM responses,
without making any LLM API calls. It uses the same MorphCloud infrastructure as the
original run to ensure consistent Lean environment.

Usage:
    poetry run python -m sorrydb.cli.run_morphcloud_replay \
      --responses-file llm_responses_for_replay.json \
      --sorry-file data/.../sorries.json \
      --output-dir replay_results/ \
      --max-workers 25
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from dotenv import find_dotenv, load_dotenv
from git import Repo
import httpx
from morphcloud.api import ApiError, Instance, MorphCloudClient
from paramiko.ssh_exception import SSHException, ChannelException

from sorrydb.runners.json_runner import load_sorry_json
from sorrydb.database.sorry import FailedSorry, RepoInfo, Sorry, SorryJSONEncoder, SorryResult
from sorrydb.utils.git_ops import sanitize_repo_name
from sorrydb.utils.logging import setup_logger

# Import common functions from morphcloud_runner
from sorrydb.runners.morphcloud_runner import (
    _create_cache_retry_step,
    _get_log_path,
    _calculate_sorry_stats,
    _poll_for_result_file,
    MORPH_API_KEY,
    BUILD_TIMEOUT,
    MAX_BUILD_RETRIES,
    PROCESS_SORRY_TIMEOUT,
    FILE_OP_TIMEOUT,
    POLL_INTERVAL,
)

load_dotenv()

FINAL_OUTPUT_NAME = "result.json"
RUN_SUMMARY_NAME = "run_summary.json"

# Global counter for tracking concurrent builds
_concurrent_builds = 0
_concurrent_builds_lock = asyncio.Lock()


async def _process_single_sorry_replay_async(
    mc: MorphCloudClient,
    sorry: Sorry,
    snapshot_id: str,
    llm_responses: list[str],
    output_dir: Path,
    index: int,
    total: int,
    debug_extraction: bool = False,
) -> list[SorryResult]:
    """Async function to process a single sorry on a MorphCloud instance in REPLAY mode.

    Instead of calling an LLM strategy, this passes pre-stored LLM responses
    to run_morphcloud_local.py via --replay-responses.

    Args:
        mc: Shared MorphCloudClient instance
        sorry: The sorry to process
        snapshot_id: Pre-built snapshot ID to use for this sorry's repository
        llm_responses: List of pre-stored LLM response strings
        output_dir: Directory to save output files
        index: Current index (1-based) for progress tracking
        total: Total number of sorries being processed
    """
    log_path = _get_log_path("process_single_sorry", f"{sorry.id}_replay.log", output_dir)

    with setup_logger(f"process_sorry_replay_{sorry.id}", log_path) as logger:
        repo_name = sanitize_repo_name(sorry.repo.remote)
        commit_short = sorry.repo.commit[:12] if sorry.repo.commit else "unknown"
        print(f"[{index}/{total}] Replay {sorry.id} ({repo_name}@{commit_short}) with {len(llm_responses)} responses")

        logger.info(f"[process_single_sorry_replay] Starting replay for sorry {sorry.id}")
        logger.info(f"[process_single_sorry_replay] Using snapshot: {snapshot_id}")
        logger.info(f"[process_single_sorry_replay] LLM responses to replay: {len(llm_responses)}")

        # Create descriptive instance name
        instance_name = f"{repo_name}_{commit_short}_replay_{sorry.id}"

        for attempt in range(1, 4):  # 3 attempts total
            logger.info(f"[process_single_sorry_replay] Starting attempt {attempt}/3")
            try:
                logger.info("[process_single_sorry_replay] Starting instance from snapshot...")
                with await mc.instances.astart(
                    snapshot_id=snapshot_id,
                    ttl_seconds=PROCESS_SORRY_TIMEOUT + 120,
                    timeout=PROCESS_SORRY_TIMEOUT + 60,
                    metadata={
                        "name": instance_name,
                        "repo": sorry.repo.remote,
                        "commit": sorry.repo.commit,
                        "strategy": "replay",
                        "sorry_id": sorry.id
                    }
                ) as instance:
                    logger.info(f"[process_single_sorry_replay] Instance started: {instance.id}")

                    # Create .env file using aexec
                    logger.info("[process_single_sorry_replay] Creating .env file...")
                    with open(find_dotenv(), "r") as f:
                        env_content = f.read()
                    create_env_cmd = f"cat > SorryDB/.env << 'EOF'\n{env_content}\nEOF"
                    try:
                        env_result = await asyncio.wait_for(instance.aexec(create_env_cmd), timeout=FILE_OP_TIMEOUT)
                    except asyncio.TimeoutError as e:
                        raise TimeoutError(f"Creating .env file timed out after {FILE_OP_TIMEOUT} seconds") from e
                    logger.info(f"[process_single_sorry_replay] .env file created (exit_code: {env_result.exit_code})")

                    # Prepare JSON arguments, escaping single quotes for bash
                    sorry_json = json.dumps(sorry, cls=SorryJSONEncoder).replace("'", "'\"'\"'")

                    # Upload replay responses as a file (too large for command line args)
                    responses_json_str = json.dumps(llm_responses)
                    responses_file_path = "/root/replay_responses.json"
                    logger.info(f"[process_single_sorry_replay] Uploading {len(responses_json_str)} bytes of replay responses...")

                    # Write responses to a temp file locally, then upload
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
                        tmp_file.write(responses_json_str)
                        tmp_file_path = tmp_file.name

                    try:
                        await asyncio.wait_for(
                            instance.aupload(tmp_file_path, responses_file_path),
                            timeout=FILE_OP_TIMEOUT
                        )
                        logger.info(f"[process_single_sorry_replay] Replay responses uploaded to {responses_file_path}")
                    except asyncio.TimeoutError as e:
                        raise TimeoutError(f"Uploading replay responses timed out after {FILE_OP_TIMEOUT} seconds") from e
                    finally:
                        # Clean up temp file
                        import os
                        os.unlink(tmp_file_path)

                    cmd = (
                        f"cd SorryDB && "
                        f'export PATH="$HOME/.local/bin:$PATH" && '
                        f'export PATH="$HOME/.elan/bin:$PATH" && '
                        f"poetry run python -m sorrydb.cli.run_morphcloud_local "
                        f"--repo-path ~/repo "
                        f"--sorry-json '{sorry_json}' "
                        f"--replay-responses-file '{responses_file_path}'"
                    )
                    if debug_extraction:
                        cmd += " --debug-extraction"
                    logger.info("[process_single_sorry_replay] Executing replay command...")

                    # Create both tasks: main aexec and polling for result file
                    main_task = asyncio.create_task(
                        instance.aexec(cmd, PROCESS_SORRY_TIMEOUT),
                        name="main_aexec"
                    )
                    poll_task = asyncio.create_task(
                        _poll_for_result_file(instance, "/root/repo/result.json", POLL_INTERVAL, logger),
                        name="poll_result"
                    )

                    timeout_error = None
                    download_run_log = False

                    try:
                        done, pending = await asyncio.wait(
                            [main_task, poll_task],
                            timeout=PROCESS_SORRY_TIMEOUT,
                            return_when=asyncio.FIRST_COMPLETED
                        )

                        for task in pending:
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass

                        if main_task in done:
                            res = main_task.result()
                            logger.info(f"[process_single_sorry_replay] Command completed (exit_code: {res.exit_code})")
                            logger.info(f"[process_single_sorry_replay] STDOUT:\n{res.stdout}")
                            if res.stderr:
                                logger.info(f"[process_single_sorry_replay] STDERR:\n{res.stderr}")
                        elif poll_task in done:
                            logger.info("[process_single_sorry_replay] Result file detected via polling")
                            download_run_log = True
                        else:
                            timeout_error = TimeoutError(f"Command timed out after {PROCESS_SORRY_TIMEOUT}s")

                    except asyncio.TimeoutError:
                        timeout_error = TimeoutError(f"Command timed out after {PROCESS_SORRY_TIMEOUT}s")

                    # Download run.log if needed
                    if download_run_log or timeout_error:
                        run_log_path = _get_log_path("remote_morph_logs", f"{sorry.id}_replay_attempt_{attempt}_run.log", output_dir)
                        try:
                            await asyncio.wait_for(
                                instance.adownload("/root/repo/run.log", str(run_log_path)),
                                timeout=FILE_OP_TIMEOUT
                            )
                            logger.info(f"[process_single_sorry_replay] Downloaded run.log to {run_log_path}")
                        except Exception as e:
                            logger.warning(f"[process_single_sorry_replay] Failed to download run.log: {e}")

                    if timeout_error:
                        raise timeout_error

                    # Download result file
                    logger.info("[process_single_sorry_replay] Downloading result file...")
                    individual_dir = output_dir / "individual"
                    individual_dir.mkdir(parents=True, exist_ok=True)
                    output_path = individual_dir / f"{sorry.id}_replay.json"
                    try:
                        await asyncio.wait_for(
                            instance.adownload("/root/repo/result.json", str(output_path)),
                            timeout=FILE_OP_TIMEOUT
                        )
                    except asyncio.TimeoutError as e:
                        raise TimeoutError(f"Download timed out after {FILE_OP_TIMEOUT}s") from e
                    logger.info(f"[process_single_sorry_replay] Downloaded result to {output_path}")

                    # Download debug extraction file if enabled
                    if debug_extraction:
                        debug_dir = output_dir / "debug_extraction"
                        debug_dir.mkdir(parents=True, exist_ok=True)
                        debug_output_path = debug_dir / f"{sorry.id}.json"
                        try:
                            await asyncio.wait_for(
                                instance.adownload("/root/repo/debug_extraction.json", str(debug_output_path)),
                                timeout=FILE_OP_TIMEOUT
                            )
                            logger.info(f"[process_single_sorry_replay] Downloaded debug extraction to {debug_output_path}")
                        except Exception as e:
                            logger.warning(f"[process_single_sorry_replay] Failed to download debug extraction file: {e}")

                logger.info("[process_single_sorry_replay] Instance context closed")

                # Parse and return result
                logger.info("[process_single_sorry_replay] Parsing result file...")
                with open(output_path, "r") as f:
                    result_data = json.load(f)

                if isinstance(result_data, dict):
                    print(f"[{index}/{total}] Completed replay {sorry.id}")
                    return [SorryResult(**result_data)]
                elif isinstance(result_data, list) and len(result_data) > 0:
                    print(f"[{index}/{total}] Completed replay {sorry.id} ({len(result_data)} results)")
                    return [SorryResult(**r) for r in result_data]
                else:
                    logger.error(f"[process_single_sorry_replay] Unexpected format: {type(result_data)}")
                    print(f"[{index}/{total}] Failed replay {sorry.id}: unexpected format")
                    return [SorryResult(
                        sorry=sorry,
                        proof=None,
                        proof_verified=False,
                        success=False,
                        error_type="unexpected_format",
                        error_message=f"Unexpected result format: {type(result_data)}",
                    )]

            except (TimeoutError, httpx.NetworkError, ApiError, SSHException) as e:
                logger.error(f"[process_single_sorry_replay] Retryable error on attempt {attempt}/3: {e}")
                print(f"[{index}/{total}] {type(e).__name__} {sorry.id} (attempt {attempt}/3)")
                if attempt < 3:
                    await asyncio.sleep(2)
                    continue
                else:
                    print(f"[{index}/{total}] Failed replay {sorry.id}: {type(e).__name__} (3 attempts)")
                    return [SorryResult(
                        sorry=sorry,
                        proof=None,
                        proof_verified=False,
                        success=False,
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )]

            except Exception as e:
                logger.error(f"[process_single_sorry_replay] Non-retryable exception: {e}")
                print(f"[{index}/{total}] Failed replay {sorry.id}: {type(e).__name__}")
                return [SorryResult(
                    sorry=sorry,
                    proof=None,
                    proof_verified=False,
                    success=False,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )]


async def _prepare_repository_async(mc: MorphCloudClient, repo: RepoInfo, output_dir: Path | None = None) -> dict:
    """Async function to prepare a repository snapshot.

    Reuses most logic from morphcloud_runner but simplified for replay.
    """
    try:
        repo_name = sanitize_repo_name(repo.remote)
        commit_short = (repo.commit or "unknown")[:12]
        log_path = _get_log_path("prepare_repository", f"{repo_name}_{commit_short}_replay.log", output_dir)

        with setup_logger(f"prepare_repo_replay_{repo_name}_{commit_short}", log_path) as logger:
            logger.info(f"[prepare_repository] Starting for {repo_name}")

            snapshot_name = f"{repo_name}_{commit_short}_replay"

            logger.info("[prepare_repository] Creating snapshot...")
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
                return {
                    "snapshot_id": None,
                    "remote": repo.remote,
                    "commit": repo.commit,
                    "error_message": error_message,
                }

            logger.info(f"[prepare_repository] Snapshot created: {snap.id}")

            # Get SorryDB commit for checkout
            try:
                git_repo = Repo(".")
                sorrydb_commit_ref = git_repo.head.commit.hexsha
            except Exception:
                sorrydb_commit_ref = "HEAD"

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
            error_message = None
            global _concurrent_builds

            try:
                async with _concurrent_builds_lock:
                    _concurrent_builds += 1

                build_start_time = time.time()
                snapshot_id = None

                for build_attempt in range(1, MAX_BUILD_RETRIES + 1):
                    try:
                        logger.info(f"[prepare_repository] Build attempt {build_attempt}/{MAX_BUILD_RETRIES}")
                        result = await asyncio.wait_for(
                            snap.abuild(steps=steps),
                            timeout=BUILD_TIMEOUT
                        )
                        snapshot_id = result.id
                        build_duration = time.time() - build_start_time
                        logger.info(f"[prepare_repository] Build finished: {snapshot_id} ({build_duration:.1f}s)")
                        break

                    except asyncio.TimeoutError:
                        if build_attempt == MAX_BUILD_RETRIES:
                            error_message = f"Build timed out after {BUILD_TIMEOUT}s"
                            logger.error(f"[prepare_repository] {error_message}")

            except Exception as e:
                error_message = f"Exception during build: {str(e)}"
                logger.error(f"[prepare_repository] {error_message}")

            finally:
                async with _concurrent_builds_lock:
                    _concurrent_builds -= 1

            return {
                "snapshot_id": snapshot_id,
                "remote": repo.remote,
                "commit": repo.commit,
                "error_message": error_message,
            }
    except Exception as e:
        return {
            "snapshot_id": None,
            "remote": repo.remote,
            "commit": repo.commit,
            "error_message": f"Exception during preparation: {str(e)}",
        }


def _create_run_summary(
    responses_file: Path,
    sorry_file: Path,
    max_workers: int,
    start_time: datetime,
    end_time: datetime,
    total_sorries: int,
    sorries_with_responses: int,
    results: list[SorryResult],
) -> dict:
    """Create a summary dictionary for the replay run."""
    # Get SorryDB commit info
    try:
        git_repo = Repo(".")
        sorrydb_commit = git_repo.head.commit.hexsha
        sorrydb_branch = git_repo.active_branch.name
    except Exception:
        sorrydb_commit = "unknown"
        sorrydb_branch = "unknown"

    duration_seconds = (end_time - start_time).total_seconds()
    stats = _calculate_sorry_stats(results)

    return {
        "run_metadata": {
            "mode": "replay",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration_seconds,
            "duration_human": f"{int(duration_seconds // 60)}m {int(duration_seconds % 60)}s",
        },
        "sorrydb_info": {
            "branch": sorrydb_branch,
            "commit": sorrydb_commit,
        },
        "input": {
            "responses_file": str(responses_file),
            "sorry_file": str(sorry_file),
        },
        "execution": {
            "max_workers": max_workers,
        },
        "results": {
            "total_sorries_in_file": total_sorries,
            "sorries_with_responses": sorries_with_responses,
            "unique_sorries_processed": stats['unique_sorries'],
            "unique_sorries_verified": stats['unique_verified'],
            "failed_processing": stats['unique_failed'],
            "total_results": stats['total_results'],
            "verified_results": stats['verified_results'],
        },
    }


async def run_replay(
    responses_file: Path,
    sorry_file: Path,
    output_dir: Path,
    max_workers: int,
    logger: logging.Logger,
    debug_extraction: bool = False,
):
    """Main replay function."""
    start_time = datetime.now()
    logger.info(f"Replay run started at {start_time.isoformat()}")

    # Load responses file
    logger.info(f"Loading responses from {responses_file}")
    with open(responses_file) as f:
        responses_data = json.load(f)

    sorry_responses = responses_data.get("sorry_responses", {})
    logger.info(f"Loaded responses for {len(sorry_responses)} sorries")

    # Load sorries file
    logger.info(f"Loading sorries from {sorry_file}")
    sorries = load_sorry_json(sorry_file)
    logger.info(f"Loaded {len(sorries)} sorries from file")

    # Filter to sorries that have responses
    sorries_with_responses = []
    for sorry in sorries:
        if sorry.id in sorry_responses:
            llm_responses = sorry_responses[sorry.id].get("llm_responses", [])
            if llm_responses:
                sorries_with_responses.append((sorry, llm_responses))
            else:
                logger.warning(f"Sorry {sorry.id} has no LLM responses, skipping")
        else:
            logger.warning(f"Sorry {sorry.id} not found in responses file, skipping")

    logger.info(f"Found {len(sorries_with_responses)} sorries with responses to replay")

    if not sorries_with_responses:
        logger.error("No sorries with responses found, exiting")
        return []

    # Create MorphCloud client
    mc = MorphCloudClient(api_key=MORPH_API_KEY)

    # Get unique repos
    remote_commit_pairs = {(s.repo.remote, s.repo.commit): s.repo for s, _ in sorries_with_responses}
    repos = list(remote_commit_pairs.values())
    logger.info(f"Found {len(repos)} unique repositories to prepare")

    # Prepare repository snapshots
    print(f"Preparing {len(repos)} repository snapshots...")
    semaphore = asyncio.Semaphore(max_workers)

    async def prepare_with_limit(repo: RepoInfo):
        async with semaphore:
            return await _prepare_repository_async(mc, repo, output_dir)

    tasks = [prepare_with_limit(repo) for repo in repos]
    prep_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Build snapshot mapping
    snapshot_mapping = {}
    prepared_sorries = []

    for result in prep_results:
        if isinstance(result, Exception):
            logger.error(f"Exception during preparation: {result}")
            continue

        repo_key = (result["remote"], result["commit"])
        if result["snapshot_id"]:
            snapshot_mapping[repo_key] = result["snapshot_id"]
            # Add sorries with this repo
            for sorry, responses in sorries_with_responses:
                if sorry.repo.remote == result["remote"] and sorry.repo.commit == result["commit"]:
                    prepared_sorries.append((sorry, responses))
        else:
            logger.error(f"Build failed for {result['remote']}: {result.get('error_message')}")

    logger.info(f"Prepared {len(prepared_sorries)} sorries with {len(snapshot_mapping)} snapshots")

    if not prepared_sorries:
        logger.error("No sorries could be prepared, exiting")
        return []

    # Process sorries
    print(f"Processing {len(prepared_sorries)} sorries in replay mode...")

    async def process_with_limit(sorry: Sorry, llm_responses: list[str], index: int, total: int):
        repo_key = (sorry.repo.remote, sorry.repo.commit)
        snapshot_id = snapshot_mapping[repo_key]
        async with semaphore:
            return await _process_single_sorry_replay_async(
                mc, sorry, snapshot_id, llm_responses, output_dir, index, total,
                debug_extraction=debug_extraction
            )

    tasks = [
        process_with_limit(sorry, responses, idx + 1, len(prepared_sorries))
        for idx, (sorry, responses) in enumerate(prepared_sorries)
    ]
    nested_results = await asyncio.gather(*tasks)

    # Flatten results
    results = [r for sublist in nested_results for r in sublist]

    # Calculate stats
    stats = _calculate_sorry_stats(results)
    logger.info(f"Replay complete: {stats['unique_verified']}/{stats['unique_sorries']} verified")

    # Save results
    result_path = output_dir / FINAL_OUTPUT_NAME
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, cls=SorryJSONEncoder, ensure_ascii=False)
    logger.info(f"Results saved to {result_path}")

    # Save run summary
    end_time = datetime.now()
    summary = _create_run_summary(
        responses_file=responses_file,
        sorry_file=sorry_file,
        max_workers=max_workers,
        start_time=start_time,
        end_time=end_time,
        total_sorries=len(sorries),
        sorries_with_responses=len(sorries_with_responses),
        results=results,
    )
    summary_path = output_dir / RUN_SUMMARY_NAME
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4, ensure_ascii=False)
    logger.info(f"Summary saved to {summary_path}")

    print(f"\nReplay complete: {stats['unique_verified']}/{stats['unique_sorries']} sorries verified")
    print(f"Results saved to {output_dir}")

    return results


async def main():
    parser = argparse.ArgumentParser(
        description="Run replay verification on MorphCloud instances"
    )
    parser.add_argument(
        "--responses-file",
        type=str,
        required=True,
        help="Path to llm_responses_for_replay.json (from extract_llm_responses_for_replay.py)",
    )
    parser.add_argument(
        "--sorry-file",
        type=str,
        required=True,
        help="Path to the original sorry JSON file",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="replay_outputs",
        help="Directory to save results (default: replay_outputs)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum number of concurrent workers (default: 4)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)",
    )
    parser.add_argument(
        "--debug-extraction",
        action="store_true",
        default=False,
        help="Output per-sorry debug JSON files containing LLM response, context, and extracted proof",
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Create output directory with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = Path(args.output_dir) / f"{timestamp}_replay"
    output_dir.mkdir(parents=True, exist_ok=True)

    responses_file = Path(args.responses_file)
    sorry_file = Path(args.sorry_file)

    if not responses_file.exists():
        logger.error(f"Responses file not found: {responses_file}")
        return 1

    if not sorry_file.exists():
        logger.error(f"Sorry file not found: {sorry_file}")
        return 1

    logger.info(f"Responses file: {responses_file}")
    logger.info(f"Sorry file: {sorry_file}")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Max workers: {args.max_workers}")

    try:
        await run_replay(
            responses_file=responses_file,
            sorry_file=sorry_file,
            output_dir=output_dir,
            max_workers=args.max_workers,
            logger=logger,
            debug_extraction=args.debug_extraction,
        )
        return 0
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.exception(e)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
