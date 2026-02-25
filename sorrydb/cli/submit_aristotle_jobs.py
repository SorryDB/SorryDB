#!/usr/bin/env python3
"""CLI script to submit Aristotle jobs and record project IDs immediately.

This script:
1. Loads sorries from a JSON file
2. Prepares repository snapshots on MorphCloud (reusing existing logic)
3. For each sorry, spawns a MorphCloud instance and runs submit_aristotle_local.py
4. Collects all project IDs and writes them to aristotle_projects.json
5. Exits once all jobs are submitted (does NOT wait for Aristotle to complete)

Usage:
    poetry run python -m sorrydb.cli.submit_aristotle_jobs \
        --sorry-file doc/sample_sorry_list.json \
        --max-workers 10 \
        --output-dir outputs/aristotle_v2
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from morphcloud.api import MorphCloudClient

from ..runners.json_runner import load_sorry_json
from ..runners.morphcloud_runner import (
    _prepare_repository_async,
    FILE_OP_TIMEOUT,
    MORPH_API_KEY,
)
from ..database.sorry import FailedSorry, RepoInfo, Sorry, SorryJSONEncoder
from ..utils.git_ops import sanitize_repo_name

load_dotenv()

# Timeout for instance operations (shorter than full prover since we're just submitting)
SUBMIT_TIMEOUT = 600  # 10 minutes should be plenty for just submitting


async def _submit_single_sorry_async(
    mc: MorphCloudClient,
    sorry: Sorry,
    snapshot_id: str,
    output_dir: Path,
    index: int,
    total: int,
    logger: logging.Logger,
) -> dict:
    """Submit a single sorry to Aristotle and return project info.

    Args:
        mc: Shared MorphCloudClient instance
        sorry: The sorry to process
        snapshot_id: Pre-built snapshot ID to use for this sorry's repository
        output_dir: Directory to save output files
        index: Current index (1-based) for progress tracking
        total: Total number of sorries being processed
        logger: Logger instance

    Returns:
        Dictionary with submission result including project_id or error
    """
    repo_name = sanitize_repo_name(sorry.repo.remote)
    commit_short = sorry.repo.commit[:12] if sorry.repo.commit else "unknown"
    instance_name = f"aristotle_submit_{repo_name}_{commit_short}_{sorry.id}"

    print(f"[{index}/{total}] Submitting {sorry.id} ({repo_name}@{commit_short})")
    logger.info(f"[submit_single_sorry] Starting for sorry {sorry.id}")
    logger.info(f"[submit_single_sorry] Using snapshot: {snapshot_id}")

    for attempt in range(1, 4):  # 3 attempts
        try:
            logger.info(f"[submit_single_sorry] Attempt {attempt}/3")

            with await mc.instances.astart(
                snapshot_id=snapshot_id,
                ttl_seconds=SUBMIT_TIMEOUT + 120,
                timeout=SUBMIT_TIMEOUT + 60,
                metadata={
                    "name": instance_name,
                    "repo": sorry.repo.remote,
                    "commit": sorry.repo.commit,
                    "sorry_id": sorry.id,
                    "purpose": "aristotle_submit",
                }
            ) as instance:
                logger.info(f"[submit_single_sorry] Instance started: {instance.id}")

                # Create .env file on the instance
                logger.info("[submit_single_sorry] Creating .env file...")
                with open(find_dotenv(), "r") as f:
                    env_content = f.read()

                # Handle GOOGLE_APPLICATION_CREDENTIALS
                gcp_creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
                if gcp_creds_path and os.path.exists(gcp_creds_path):
                    logger.info(f"[submit_single_sorry] Copying GCP credentials...")
                    remote_creds_path = "/root/gcp-sa-key.json"

                    with open(gcp_creds_path, "r") as f:
                        gcp_key_content = f.read()

                    create_key_cmd = f"cat > {remote_creds_path} << 'GCPEOF'\n{gcp_key_content}\nGCPEOF"
                    try:
                        await asyncio.wait_for(instance.aexec(create_key_cmd), timeout=FILE_OP_TIMEOUT)
                    except asyncio.TimeoutError:
                        raise TimeoutError(f"Creating GCP key file timed out")

                    env_content = re.sub(
                        r"GOOGLE_APPLICATION_CREDENTIALS=.*",
                        f"GOOGLE_APPLICATION_CREDENTIALS={remote_creds_path}",
                        env_content
                    )

                create_env_cmd = f"cat > SorryDB/.env << 'EOF'\n{env_content}\nEOF"
                try:
                    await asyncio.wait_for(instance.aexec(create_env_cmd), timeout=FILE_OP_TIMEOUT)
                except asyncio.TimeoutError:
                    raise TimeoutError(f"Creating .env file timed out")

                # Prepare JSON arguments, escaping single quotes for bash
                sorry_json = json.dumps(sorry, cls=SorryJSONEncoder).replace("'", "'\"'\"'")

                cmd = (
                    f"cd SorryDB && "
                    f'export PATH="$HOME/.local/bin:$PATH" && '
                    f'export PATH="$HOME/.elan/bin:$PATH" && '
                    f"poetry run python -m sorrydb.cli.submit_aristotle_local "
                    f"--repo-path ~/repo "
                    f"--sorry-json '{sorry_json}'"
                )

                logger.info("[submit_single_sorry] Running submit_aristotle_local...")
                try:
                    result = await asyncio.wait_for(
                        instance.aexec(cmd, SUBMIT_TIMEOUT),
                        timeout=SUBMIT_TIMEOUT
                    )
                    logger.info(f"[submit_single_sorry] Command completed (exit_code: {result.exit_code})")
                    if result.stdout:
                        logger.info(f"[submit_single_sorry] STDOUT:\n{result.stdout}")
                    if result.stderr:
                        logger.info(f"[submit_single_sorry] STDERR:\n{result.stderr}")
                except asyncio.TimeoutError:
                    raise TimeoutError(f"Submit command timed out after {SUBMIT_TIMEOUT}s")

                # Download result file
                individual_dir = output_dir / "individual"
                individual_dir.mkdir(parents=True, exist_ok=True)
                output_path = individual_dir / f"{sorry.id}_submit.json"

                try:
                    await asyncio.wait_for(
                        instance.adownload("/root/repo/aristotle_submit.json", str(output_path)),
                        timeout=FILE_OP_TIMEOUT
                    )
                    logger.info(f"[submit_single_sorry] Downloaded result to {output_path}")
                except asyncio.TimeoutError:
                    raise TimeoutError(f"Downloading result file timed out")

            # Parse and return result
            with open(output_path, "r") as f:
                submit_result = json.load(f)

            # Add repo info to result
            submit_result["repo_remote"] = sorry.repo.remote
            submit_result["repo_commit"] = sorry.repo.commit
            submit_result["sorry_file_path"] = sorry.location.path

            if submit_result.get("success"):
                print(f"[{index}/{total}] Submitted {sorry.id}: {submit_result.get('aristotle_project_id')}")
            else:
                print(f"[{index}/{total}] Failed {sorry.id}: {submit_result.get('error')}")

            return submit_result

        except Exception as e:
            logger.error(f"[submit_single_sorry] Error on attempt {attempt}: {type(e).__name__}: {e}")
            if attempt < 3:
                backoff_delay = 5 * (2 ** (attempt - 1))
                logger.info(f"[submit_single_sorry] Retrying in {backoff_delay}s...")
                await asyncio.sleep(backoff_delay)
            else:
                print(f"[{index}/{total}] Failed {sorry.id}: {type(e).__name__}")
                return {
                    "sorry_id": sorry.id,
                    "aristotle_project_id": None,
                    "submitted_at": datetime.now().isoformat(),
                    "success": False,
                    "error": f"{type(e).__name__}: {str(e)}",
                    "repo_remote": sorry.repo.remote,
                    "repo_commit": sorry.repo.commit,
                    "sorry_file_path": sorry.location.path,
                }


async def submit_aristotle_jobs(
    sorry_json_path: Path,
    output_dir: Path,
    max_workers: int,
    logger: logging.Logger,
) -> dict:
    """Submit all sorries to Aristotle and collect project IDs.

    Args:
        sorry_json_path: Path to JSON file containing sorries
        output_dir: Directory to save results
        max_workers: Maximum concurrent workers
        logger: Logger instance

    Returns:
        Dictionary with all submission results
    """
    start_time = datetime.now()
    logger.info(f"[submit_aristotle_jobs] Started at {start_time.isoformat()}")

    # Load sorries
    logger.info(f"[submit_aristotle_jobs] Loading sorries from {sorry_json_path}")
    sorries = load_sorry_json(sorry_json_path)
    logger.info(f"[submit_aristotle_jobs] Loaded {len(sorries)} sorries")

    # Create shared MorphCloud client
    mc = MorphCloudClient(api_key=MORPH_API_KEY)
    logger.info(f"[submit_aristotle_jobs] Created MorphCloudClient")

    # Prepare repository snapshots
    logger.info(f"[submit_aristotle_jobs] Preparing repository snapshots...")
    remote_commit_pairs = {(s.repo.remote, s.repo.commit): s.repo for s in sorries}
    repos = list(remote_commit_pairs.values())
    logger.info(f"[submit_aristotle_jobs] Found {len(repos)} unique repositories")

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(max_workers)

    async def prepare_with_limit(repo: RepoInfo):
        async with semaphore:
            return await _prepare_repository_async(mc, repo, output_dir)

    # Prepare all repositories concurrently
    print(f"Preparing {len(repos)} repository snapshots with {max_workers} workers...")
    tasks = [prepare_with_limit(repo) for repo in repos]
    prep_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Build snapshot mapping
    snapshot_mapping: dict[tuple[str, str], str] = {}
    failed_builds: list[FailedSorry] = []
    prepared_sorries: list[Sorry] = []

    for idx, result in enumerate(prep_results):
        if isinstance(result, Exception):
            logger.error(f"[submit_aristotle_jobs] Exception during preparation: {result}")
            continue

        repo_key = (result["remote"], result["commit"])

        if result["snapshot_id"] is not None:
            snapshot_mapping[repo_key] = result["snapshot_id"]
            logger.info(f"[submit_aristotle_jobs] Snapshot ready: {result['snapshot_id']}")
            for s in sorries:
                if s.repo.remote == result["remote"] and s.repo.commit == result["commit"]:
                    prepared_sorries.append(s)
        else:
            error_msg = result.get("error_message", "Unknown build failure")
            logger.error(f"[submit_aristotle_jobs] Build failed: {error_msg}")
            for s in sorries:
                if s.repo.remote == result["remote"] and s.repo.commit == result["commit"]:
                    failed_builds.append(FailedSorry(
                        sorry=s,
                        failure_reason=error_msg,
                        failure_type="build_failure"
                    ))

    print(f"Prepared {len(prepared_sorries)} sorries ({len(failed_builds)} failed builds)")
    logger.info(f"[submit_aristotle_jobs] {len(prepared_sorries)} sorries ready, {len(failed_builds)} failed")

    # Submit all prepared sorries to Aristotle
    async def submit_with_limit(sorry: Sorry, index: int, total: int):
        repo_key = (sorry.repo.remote, sorry.repo.commit)
        snapshot_id = snapshot_mapping[repo_key]
        async with semaphore:
            return await _submit_single_sorry_async(
                mc, sorry, snapshot_id, output_dir, index, total, logger
            )

    print(f"Submitting {len(prepared_sorries)} sorries to Aristotle...")
    submit_tasks = [
        submit_with_limit(sorry, idx + 1, len(prepared_sorries))
        for idx, sorry in enumerate(prepared_sorries)
    ]
    submit_results = await asyncio.gather(*submit_tasks, return_exceptions=True)

    # Collect results
    successful_submissions = []
    failed_submissions = []

    for result in submit_results:
        if isinstance(result, Exception):
            failed_submissions.append({
                "error": f"{type(result).__name__}: {str(result)}",
                "submitted_at": datetime.now().isoformat(),
            })
        elif result.get("success"):
            successful_submissions.append(result)
        else:
            failed_submissions.append(result)

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # Create final output
    output = {
        "job_run_timestamp": start_time.isoformat(),
        "job_end_timestamp": end_time.isoformat(),
        "duration_seconds": duration,
        "duration_human": f"{int(duration // 60)}m {int(duration % 60)}s",
        "sorry_file": str(sorry_json_path),
        "output_dir": str(output_dir),
        "total_sorries": len(sorries),
        "prepared_sorries": len(prepared_sorries),
        "failed_builds": len(failed_builds),
        "successful_submissions": len(successful_submissions),
        "failed_submissions": len(failed_submissions),
        "projects": successful_submissions,
        "failed": failed_submissions,
        "build_failures": [
            {
                "sorry_id": fs.sorry.id,
                "error": fs.failure_reason,
            }
            for fs in failed_builds
        ],
    }

    return output


async def main():
    parser = argparse.ArgumentParser(
        description="Submit Aristotle jobs and record project IDs immediately (without waiting for completion)"
    )
    parser.add_argument(
        "--sorry-file",
        type=str,
        required=True,
        help="Path to the sorry JSON file",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs/aristotle_v2",
        help="Directory to save results (default: outputs/aristotle_v2)",
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

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Convert paths
    sorry_file = Path(args.sorry_file)
    base_output_dir = Path(args.output_dir)

    # Create timestamped output directory
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = base_output_dir / f"{timestamp}_aristotle_submit"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Processing sorries from: {sorry_file}")
    logger.info(f"Max workers: {args.max_workers}")
    logger.info(f"Output directory: {output_dir}")

    try:
        result = await submit_aristotle_jobs(
            sorry_json_path=sorry_file,
            output_dir=output_dir,
            max_workers=args.max_workers,
            logger=logger,
        )

        # Write results to file
        output_path = output_dir / "aristotle_projects.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\n{'=' * 60}")
        print(f"Aristotle Job Submission Complete")
        print(f"{'=' * 60}")
        print(f"Total sorries: {result['total_sorries']}")
        print(f"Prepared: {result['prepared_sorries']}")
        print(f"Build failures: {result['failed_builds']}")
        print(f"Submitted: {result['successful_submissions']}")
        print(f"Submit failures: {result['failed_submissions']}")
        print(f"Duration: {result['duration_human']}")
        print(f"Results saved to: {output_path}")
        print(f"{'=' * 60}")

        return 0

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.exception(e)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
