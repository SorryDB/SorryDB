import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from git import Repo
from morphcloud.api import MorphCloudClient

from ..runners.json_runner import load_sorry_json
from ..database.sorry import FailedSorry, RepoInfo, Sorry, SorryJSONEncoder, SorryResult
from ..utils.git_ops import github_commit_exists, parse_remote, sanitize_repo_name
from ..utils.logging import setup_logger

load_dotenv()
MORPH_API_KEY = os.environ["MORPH_API_KEY"]
FINAL_OUTPUT_NAME = "result.json"
FAILED_OUTPUT_NAME = "failed.json"
RUN_SUMMARY_NAME = "run_summary.json"


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
    successful_results: int,
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
            "successful_results": successful_results,
            "failed_processing": prepared_sorries - successful_results,
        },
    }

    return summary


async def _process_single_sorry_async(
    sorry: Sorry, snapshot_id: str, strategy_name: str, strategy_args: dict, output_dir: Path
) -> SorryResult | None:
    """Async function to process a single sorry on a MorphCloud instance.

    Args:
        sorry: The sorry to process
        snapshot_id: Pre-built snapshot ID to use for this sorry's repository
        strategy_name: Name of the strategy to use
        strategy_args: Arguments for the strategy
        output_dir: Directory to save output files
    """
    log_path = _get_log_path("process_single_sorry", f"{sorry.id}.log", output_dir)
    logger = setup_logger(f"process_sorry_{sorry.id}", log_path)

    logger.info(f"[process_single_sorry] Starting for sorry {sorry.id}")
    logger.info(f"[process_single_sorry] Using snapshot: {snapshot_id}")
    logger.info(f"[process_single_sorry] Repository: {sorry.repo.remote}@{sorry.repo.commit}")

    mc = MorphCloudClient(api_key=MORPH_API_KEY)
    logger.info("[process_single_sorry] MorphCloud client initialized")

    logger.info("[process_single_sorry] Starting instance from snapshot...")
    with await mc.instances.astart(snapshot_id=snapshot_id) as instance:
        logger.info(f"[process_single_sorry] Instance started successfully: {instance.id}")

        # Create .env file using aexec
        logger.info("[process_single_sorry] Creating .env file...")
        with open(find_dotenv(), "r") as f:
            env_content = f.read()
        create_env_cmd = f"cat > SorryDB/.env << 'EOF'\n{env_content}\nEOF"
        env_result = await instance.aexec(create_env_cmd)
        logger.info(f"[process_single_sorry] .env file created (exit_code: {env_result.exit_code})")

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
        logger.info("[process_single_sorry] Executing agent command...")
        res = await instance.aexec(cmd)
        logger.info(f"[process_single_sorry] Agent command completed (exit_code: {res.exit_code})")
        logger.info(f"[process_single_sorry] STDOUT:\n{res.stdout}")
        if res.stderr:
            logger.info(f"[process_single_sorry] STDERR:\n{res.stderr}")

        # Save individual result file for debugging
        logger.info("[process_single_sorry] Downloading result file...")
        individual_dir = output_dir / "individual"
        individual_dir.mkdir(parents=True, exist_ok=True)
        output_path = individual_dir / f"{sorry.id}.json"
        await instance.adownload("/root/repo/result.json", str(output_path))
        logger.info(f"[process_single_sorry] Downloaded result to {output_path}")

    logger.info("[process_single_sorry] Instance context closed successfully")

    # Parse and return the result directly
    logger.info("[process_single_sorry] Parsing result file...")
    try:
        with open(output_path, "r") as f:
            result_data = json.load(f)

        # Handle both dict and list formats
        if isinstance(result_data, dict):
            logger.info(f"[process_single_sorry] Successfully parsed result (dict format)")
            return SorryResult(**result_data)
        elif isinstance(result_data, list) and len(result_data) > 0:
            # If it's a list, take the first item
            logger.info(f"[process_single_sorry] Successfully parsed result (list format)")
            return SorryResult(**result_data[0])
        else:
            logger.error(f"[process_single_sorry] Unexpected result format for {sorry.id}: {type(result_data)}")
            return None
    except Exception as e:
        logger.error(f"[process_single_sorry] Failed to parse result for {sorry.id}: {e}")
        return None


async def _prepare_repository_async(repo: RepoInfo, output_dir: Path | None = None) -> dict:
    """Async function to prepare a repository snapshot."""
    mc = MorphCloudClient(api_key=MORPH_API_KEY)
    repo_name = sanitize_repo_name(repo.remote)
    commit_short = (repo.commit or "unknown")[:12]
    log_path = _get_log_path("prepare_repository", f"{repo_name}_{commit_short}.log", output_dir)
    logger = setup_logger(f"prepare_repo_{repo_name}_{commit_short}", log_path)

    logger.info(f"[prepare_repository] Starting for {sanitize_repo_name(repo.remote)}")
    logger.info(f"[prepare_repository] Repository details: remote={repo.remote}, commit={repo.commit}")

    logger.info("[prepare_repository] Creating snapshot (vcpus=4, memory=16384, disk_size=15000)...")
    snap = await mc.snapshots.acreate(vcpus=4, memory=16384, disk_size=15000, digest="sorrydb-08-10-25")
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
            "apt-get update && "
            "apt-get install -y curl git wget htop gnupg python3 python3-pip python3-venv python-is-python3 pipx python3-dev && "
            "curl https://elan.lean-lang.org/elan-init.sh -sSf | sh -s -- -y --default-toolchain leanprover/lean4:v4.21.0 && "
            "pipx install poetry"
        ),
        # Step 2: Clone and setup SorryDB
        (
            "git clone https://github.com/SorryDB/SorryDB.git && "
            "cd SorryDB && "
            f"git checkout 37b09cf126ce4a3bd1ada81c4523f7eccd4543fe && " # commit with frozen package deps
            'export PATH="$HOME/.local/bin:$PATH" && '
            "poetry install"
        ),
        # Clone target repository and build
        (
            f"git clone {repo.remote} repo && "
            f"cd repo && "
            f"git fetch origin {repo.commit} && "
            f"git checkout {repo.commit} && "
            f'export PATH="$HOME/.elan/bin:$PATH" && '
            f"(lake exe cache get || true) && "
            f"lake build"
        ),
        (
            f"cd SorryDB && "
            f'export PATH="$HOME/.local/bin:$PATH" && '
            f'export PATH="$HOME/.elan/bin:$PATH" && '
            f"git fetch && "
            f"git checkout {sorrydb_commit_ref} && " # checkout this specific commit
            f"poetry install && "
            f"eval $(poetry env activate)"
        ),
    ]

    logger.info("[prepare_repository] Running build steps...")
    logger.info(f"[prepare_repository] Total build steps: {len(steps)}")
    for i, step in enumerate(steps, 1):
        logger.info(f"[prepare_repository] Step {i}: {step[:100]}...")  # Log first 100 chars

    error_message = None
    try:
        logger.info("[prepare_repository] Starting abuild call...")
        result = await snap.abuild(steps=steps)  # type: ignore
        snapshot_id = result.id
        logger.info(f"[prepare_repository] Build finished successfully: {snapshot_id}")
    except Exception as e:
        snapshot_id = None
        error_message = f"Exception during build: {str(e)}"
        logger.error(f"[prepare_repository] {error_message}")
        logger.error(f"[prepare_repository] Exception type: {type(e).__name__}")
        logger.error(f"[prepare_repository] Exception details: {repr(e)}")
        logger.info("NOTE: Make sure to have pushed your latest commit.")

    return {
        "snapshot_id": snapshot_id,
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

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_workers)

        async def prepare_with_limit(repo: RepoInfo):
            async with semaphore:
                return await _prepare_repository_async(repo, output_dir)

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

    async def _process_sorries(self, sorries: list[Sorry], snapshot_mapping: dict[tuple[str, str], str], output_dir: Path) -> list[SorryResult | None]:
        """Process multiple sorries concurrently using async with semaphore.

        Args:
            sorries: List of sorries to process
            snapshot_mapping: Dictionary mapping (remote, commit) -> snapshot_id
            output_dir: Directory to save output files
        """
        print(f"[_process_sorries] Starting processing for {len(sorries)} sorries")
        print(f"[_process_sorries] Using {len(snapshot_mapping)} cached snapshots")

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_workers)

        async def process_with_limit(sorry: Sorry):
            # Get the snapshot ID for this sorry's repository
            repo_key = (sorry.repo.remote, sorry.repo.commit)
            snapshot_id = snapshot_mapping[repo_key]
            async with semaphore:
                return await _process_single_sorry_async(sorry, snapshot_id, self.strategy_name, self.strategy_args, output_dir)

        # Process all sorries concurrently with max_workers limit
        print(f"[_process_sorries] Starting concurrent processing with max_workers={self.max_workers}")
        tasks = [process_with_limit(sorry) for sorry in sorries]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        print(f"[_process_sorries] All processing tasks completed")

        # Convert exceptions to None
        processed_results = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"[_process_sorries] Exception during processing sorry {sorries[idx].id}: {result}")
                processed_results.append(None)
            else:
                processed_results.append(result)

        successful_count = sum(1 for r in processed_results if r is not None)
        print(f"[_process_sorries] Summary: {successful_count}/{len(processed_results)} successfully processed")
        return processed_results

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
        print(f"[process_sorries] Validating GitHub commits...")
        sorries = _validate_github_commits(sorries)
        print(f"[process_sorries] After validation: {len(sorries)} sorries")

        # Prepare repository snapshots
        print("Preparing repository snapshots...")
        sorries, build_failed_sorries, snapshot_mapping = await self._prepare_sorries(sorries, output_dir)
        print(f"Prepared {len(sorries)} sorries with {len(snapshot_mapping)} unique snapshots")

        # Save failed sorries from build stage
        if build_failed_sorries:
            print(f"Failed to build {len(build_failed_sorries)} sorries")
            # Save to timestamped output directory
            failed_path_output = output_dir / FAILED_OUTPUT_NAME
            with open(failed_path_output, "w") as f:
                json.dump(build_failed_sorries, f, indent=4, cls=SorryJSONEncoder)
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

            with open(failed_path_filter, "w") as f:
                json.dump(all_failed, f, indent=4, cls=SorryJSONEncoder)
            print(f"Merged {len(new_failures)} new failures into {failed_path_filter} (total: {len(all_failed)})")

        # Process sorries
        print("Processing sorries on MorphCloud...")
        results = await self._process_sorries(sorries, snapshot_mapping, output_dir)

        # Filter out None values (failed processing)
        successful_results = [r for r in results if r is not None]
        print(f"Successfully processed {len(successful_results)} out of {len(results)} sorries")

        # Write aggregated results directly
        result_path = output_dir / FINAL_OUTPUT_NAME
        with open(result_path, "w") as f:
            json.dump(successful_results, f, indent=4, cls=SorryJSONEncoder)
        print(f"Results saved to {result_path}")

        # Create and save run summary
        end_time = datetime.now()
        print(f"[process_sorries] Run ended at {end_time.isoformat()}")

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
            successful_results=len(successful_results),
        )

        summary_path = output_dir / RUN_SUMMARY_NAME
        with open(summary_path, "w") as f:
            json.dump(run_summary, f, indent=4)
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
