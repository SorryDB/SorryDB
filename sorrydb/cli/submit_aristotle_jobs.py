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


def _write_progress_file(
    output_path: Path,
    start_time: datetime,
    sorry_json_path: Path,
    output_dir: Path,
    total_sorries: int,
    prepared_sorries_count: int,
    failed_builds: list[FailedSorry],
    successful_submissions: list[dict],
    failed_submissions: list[dict],
    retry_info: dict | None = None,
) -> None:
    """Write current progress to the output JSON file.

    This enables crash recovery and real-time monitoring of submission status.

    Args:
        output_path: Path to write the JSON file
        start_time: When the job run started
        sorry_json_path: Path to the source sorry JSON file
        output_dir: Directory for output files
        total_sorries: Total number of sorries being processed
        prepared_sorries_count: Number of sorries that were successfully prepared
        failed_builds: List of sorries that failed during build
        successful_submissions: List of successful submission results
        failed_submissions: List of failed submission results
        retry_info: Optional dict with retry-specific fields (retry_from, original_sorry_file, etc.)
    """
    output = {
        "job_run_timestamp": start_time.isoformat(),
        "job_end_timestamp": None,  # Not finished yet
        "status": "in_progress",
        "sorry_file": str(sorry_json_path),
        "output_dir": str(output_dir),
        "total_sorries": total_sorries,
        "prepared_sorries": prepared_sorries_count,
        "failed_builds": len(failed_builds),
        "successful_submissions": len(successful_submissions),
        "failed_submissions": len(failed_submissions),
        "projects": successful_submissions,
        "failed": failed_submissions,
        "build_failures": [
            {"sorry_id": fs.sorry.id, "error": fs.failure_reason}
            for fs in failed_builds
        ],
    }

    # Add retry-specific fields if present
    if retry_info:
        output.update(retry_info)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

# Polling interval for checking Aristotle job status
ARISTOTLE_POLL_INTERVAL = 30  # seconds


async def _count_running_aristotle_jobs() -> int:
    """Count all QUEUED and IN_PROGRESS Aristotle jobs across all invocations.

    Paginates through all results to get an accurate total count.

    Returns:
        Total number of currently running Aristotle jobs
    """
    from aristotlelib import Project, ProjectStatus

    count = 0
    pagination_key = None
    while True:
        projects, next_key = await Project.list_projects(
            status=[ProjectStatus.QUEUED, ProjectStatus.IN_PROGRESS],
            limit=100,
            pagination_key=pagination_key,
        )
        count += len(projects)
        if not next_key or not projects:
            break
        pagination_key = next_key
    return count


async def _is_job_running(project_id: str) -> bool:
    """Check if an Aristotle job is still running.

    Args:
        project_id: The Aristotle project ID to check

    Returns:
        True if the job is still queued or in progress, False otherwise
    """
    import aristotlelib
    from aristotlelib import ProjectStatus

    project = await aristotlelib.Project.from_id(project_id)
    await project.refresh()
    return project.status in (ProjectStatus.QUEUED, ProjectStatus.IN_PROGRESS)


def load_previous_run(previous_run_dir: Path) -> tuple[dict, list[str], list[dict]]:
    """Load previous run data.

    Args:
        previous_run_dir: Path to the previous run's output directory

    Returns:
        - The full previous run dict
        - List of sorry_ids that failed
        - List of successful project entries to carry forward
    """
    projects_file = previous_run_dir / "aristotle_projects.json"
    with open(projects_file, "r") as f:
        data = json.load(f)

    failed_ids = [entry["sorry_id"] for entry in data.get("failed", [])]
    successful_entries = data.get("projects", [])

    return data, failed_ids, successful_entries


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
    sorries_override: list[Sorry] | None = None,
    max_concurrent_aristotle: int | None = None,
    output_path: Path | None = None,
    retry_info: dict | None = None,
) -> dict:
    """Submit all sorries to Aristotle and collect project IDs.

    Args:
        sorry_json_path: Path to JSON file containing sorries
        output_dir: Directory to save results
        max_workers: Maximum concurrent workers
        logger: Logger instance
        sorries_override: Optional list of sorries to use instead of loading from file
        max_concurrent_aristotle: Maximum concurrent Aristotle jobs (None = unlimited)
        output_path: Path to write progress file (enables incremental updates)
        retry_info: Optional dict with retry-specific fields for progress file

    Returns:
        Dictionary with all submission results
    """
    start_time = datetime.now()
    logger.info(f"[submit_aristotle_jobs] Started at {start_time.isoformat()}")

    # Load sorries (use override if provided)
    if sorries_override is not None:
        logger.info(f"[submit_aristotle_jobs] Using {len(sorries_override)} sorries from override")
        sorries = sorries_override
    else:
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
    print(f"Submitting {len(prepared_sorries)} sorries to Aristotle...")

    successful_submissions = []
    failed_submissions = []

    if max_concurrent_aristotle:
        # Rate-limited submission: check actual Aristotle job count before each submission
        logger.info(f"[submit_aristotle_jobs] Using max_concurrent_aristotle={max_concurrent_aristotle}")
        print(f"Rate-limited mode: max {max_concurrent_aristotle} concurrent Aristotle jobs")

        for idx, sorry in enumerate(prepared_sorries):
            # Wait for slot if at capacity (checks ALL running Aristotle jobs, not just ours)
            running_count = await _count_running_aristotle_jobs()
            while running_count >= max_concurrent_aristotle:
                print(
                    f"[Progress] Submitted: {len(successful_submissions)}/{len(prepared_sorries)} | "
                    f"Failed: {len(failed_submissions)} | "
                    f"Running on Aristotle: {running_count}/{max_concurrent_aristotle} (waiting for slot...)"
                )
                logger.info(
                    f"[submit_aristotle_jobs] At capacity ({running_count}/{max_concurrent_aristotle}), "
                    f"waiting for slot..."
                )
                await asyncio.sleep(ARISTOTLE_POLL_INTERVAL)
                running_count = await _count_running_aristotle_jobs()

            # Submit job
            repo_key = (sorry.repo.remote, sorry.repo.commit)
            snapshot_id = snapshot_mapping[repo_key]

            async with semaphore:
                result = await _submit_single_sorry_async(
                    mc, sorry, snapshot_id, output_dir, idx + 1, len(prepared_sorries), logger
                )

            # Track result
            if isinstance(result, Exception):
                failed_submissions.append({
                    "error": f"{type(result).__name__}: {str(result)}",
                    "submitted_at": datetime.now().isoformat(),
                })
                logger.error(f"[submit_aristotle_jobs] Submission exception: {result}")
            elif result.get("success"):
                successful_submissions.append(result)
                logger.info(
                    f"[submit_aristotle_jobs] Submitted {len(successful_submissions)}/{len(prepared_sorries)}"
                )
            else:
                failed_submissions.append(result)
                logger.warning(f"[submit_aristotle_jobs] Submission failed: {result.get('error')}")

            # Log progress after each submission
            print(
                f"[Progress] Submitted: {len(successful_submissions)}/{len(prepared_sorries)} | "
                f"Failed: {len(failed_submissions)}"
            )

            # Write progress file after each submission
            if output_path:
                _write_progress_file(
                    output_path, start_time, sorry_json_path, output_dir,
                    len(sorries), len(prepared_sorries), failed_builds,
                    successful_submissions, failed_submissions, retry_info
                )
    else:
        # Unlimited submission: submit all jobs concurrently with incremental progress
        print(f"Unlimited mode: submitting all {len(prepared_sorries)} jobs concurrently (max {max_workers} workers)")
        logger.info(f"[submit_aristotle_jobs] Unlimited mode with {max_workers} workers")

        async def submit_with_limit(sorry: Sorry, index: int, total: int):
            repo_key = (sorry.repo.remote, sorry.repo.commit)
            snapshot_id = snapshot_mapping[repo_key]
            async with semaphore:
                return await _submit_single_sorry_async(
                    mc, sorry, snapshot_id, output_dir, index, total, logger
                )

        submit_tasks = [
            asyncio.create_task(submit_with_limit(sorry, idx + 1, len(prepared_sorries)))
            for idx, sorry in enumerate(prepared_sorries)
        ]

        # Process results as they complete for incremental updates
        completed_count = 0
        for coro in asyncio.as_completed(submit_tasks):
            try:
                result = await coro
            except Exception as e:
                result = e

            completed_count += 1
            if isinstance(result, Exception):
                failed_submissions.append({
                    "error": f"{type(result).__name__}: {str(result)}",
                    "submitted_at": datetime.now().isoformat(),
                })
                logger.error(f"[submit_aristotle_jobs] Submission exception: {result}")
            elif result.get("success"):
                successful_submissions.append(result)
                logger.info(f"[submit_aristotle_jobs] Submitted {len(successful_submissions)}/{len(prepared_sorries)}")
            else:
                failed_submissions.append(result)
                logger.warning(f"[submit_aristotle_jobs] Submission failed: {result.get('error')}")

            # Log progress after each completion
            print(
                f"[Progress] Completed: {completed_count}/{len(prepared_sorries)} | "
                f"Successful: {len(successful_submissions)} | "
                f"Failed: {len(failed_submissions)}"
            )

            # Write progress file after each submission completes
            if output_path:
                _write_progress_file(
                    output_path, start_time, sorry_json_path, output_dir,
                    len(sorries), len(prepared_sorries), failed_builds,
                    successful_submissions, failed_submissions, retry_info
                )

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
        help="Path to the sorry JSON file",
    )
    parser.add_argument(
        "--retry-from",
        type=str,
        help="Path to a previous run's output directory (e.g., outputs/aristotle_v2/2026-02-25_19-58-34_aristotle_submit). "
             "Only jobs that failed in that run will be retried. Successful results will be copied over.",
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
    parser.add_argument(
        "--max-concurrent-aristotle",
        type=int,
        default=None,
        help="Max concurrent Aristotle jobs (default: unlimited). Set to 15 if hitting Aristotle limits.",
    )

    args = parser.parse_args()

    # Validate arguments: either --sorry-file or --retry-from is required
    if not args.sorry_file and not args.retry_from:
        parser.error("Either --sorry-file or --retry-from is required")
    if args.sorry_file and args.retry_from:
        parser.error("Cannot specify both --sorry-file and --retry-from")

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Convert paths
    base_output_dir = Path(args.output_dir)

    # Create timestamped output directory
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = base_output_dir / f"{timestamp}_aristotle_submit"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Handle retry mode vs normal mode
    previous_data = None
    previous_successful_entries = []
    sorries_to_process = None
    original_sorry_file = None
    total_original_sorries = 0

    if args.retry_from:
        # Retry mode: load previous run and filter to failed sorries
        previous_run_dir = Path(args.retry_from)
        logger.info(f"Retry mode: loading previous run from {previous_run_dir}")

        previous_data, failed_ids, previous_successful_entries = load_previous_run(previous_run_dir)

        # Get the original sorry file path from previous run
        original_sorry_file = Path(previous_data["sorry_file"])
        logger.info(f"Original sorry file: {original_sorry_file}")
        logger.info(f"Failed sorries to retry: {len(failed_ids)}")
        logger.info(f"Successful entries to carry forward: {len(previous_successful_entries)}")

        # Load all sorries from original file and filter to failed ones
        all_sorries = load_sorry_json(original_sorry_file)
        total_original_sorries = len(all_sorries)
        failed_ids_set = set(failed_ids)
        sorries_to_process = [s for s in all_sorries if s.id in failed_ids_set]

        print(f"Retry mode: {len(sorries_to_process)} failed sorries to retry (from {total_original_sorries} total)")
        sorry_file = original_sorry_file
    else:
        sorry_file = Path(args.sorry_file)

    logger.info(f"Processing sorries from: {sorry_file}")
    logger.info(f"Max workers: {args.max_workers}")
    logger.info(f"Output directory: {output_dir}")

    # Create output path before calling submit_aristotle_jobs for incremental updates
    output_path = output_dir / "aristotle_projects.json"

    # Build retry_info for incremental progress writes (if in retry mode)
    retry_info = None
    if args.retry_from:
        retry_info = {
            "retry_from": str(previous_run_dir),
            "original_sorry_file": str(original_sorry_file),
            "retried_sorries": len(sorries_to_process),
            "carried_forward_successful": len(previous_successful_entries),
        }

    try:
        result = await submit_aristotle_jobs(
            sorry_json_path=sorry_file,
            output_dir=output_dir,
            max_workers=args.max_workers,
            logger=logger,
            sorries_override=sorries_to_process,
            max_concurrent_aristotle=args.max_concurrent_aristotle,
            output_path=output_path,
            retry_info=retry_info,
        )

        # If in retry mode, merge results with previous successful entries
        if args.retry_from:
            all_successful = previous_successful_entries + result["projects"]
            all_failed = result["failed"]  # Only new failures remain

            result = {
                "job_run_timestamp": result["job_run_timestamp"],
                "job_end_timestamp": result["job_end_timestamp"],
                "status": "completed",
                "duration_seconds": result["duration_seconds"],
                "duration_human": result["duration_human"],
                "retry_from": str(previous_run_dir),
                "original_sorry_file": str(original_sorry_file),
                "sorry_file": str(sorry_file),
                "output_dir": str(output_dir),
                "total_sorries": total_original_sorries,
                "retried_sorries": len(sorries_to_process),
                "prepared_sorries": result["prepared_sorries"],
                "failed_builds": result["failed_builds"],
                "successful_submissions": len(all_successful),
                "failed_submissions": len(all_failed),
                "projects": all_successful,
                "failed": all_failed,
                "build_failures": result.get("build_failures", []),
            }
        else:
            # Add status: completed to non-retry results
            result["status"] = "completed"

        # Write final results to file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\n{'=' * 60}")
        print(f"Aristotle Job Submission Complete")
        print(f"{'=' * 60}")
        print(f"Total sorries: {result['total_sorries']}")
        if args.retry_from:
            print(f"Retried sorries: {result['retried_sorries']}")
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
