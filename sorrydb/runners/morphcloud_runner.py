import asyncio
import json
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from morphcloud.api import MorphCloudClient

from ..runners.json_runner import load_sorry_json
from ..database.sorry import RepoInfo, Sorry, SorryJSONEncoder, SorryResult
from ..utils.git_ops import github_commit_exists, parse_remote, sanitize_repo_name
from ..utils.logging import LogContext

load_dotenv()
MORPH_API_KEY = os.environ["MORPH_API_KEY"]
FINAL_OUTPUT_NAME = "result.json"
FAILED_OUTPUT_NAME = "failed.json"


def _get_log_path(subdirectory: str, filename: str, output_dir: Path | None = None) -> Path:
    if output_dir is not None:
        logs_root = output_dir / "logs" / subdirectory
    else:
        logs_root = Path(__file__).resolve().parents[2] / "logs" / subdirectory
    logs_root.mkdir(parents=True, exist_ok=True)
    return logs_root / filename


def _prepare_repository_sync(repo: RepoInfo, output_dir: Path | None = None) -> dict:
    """Synchronous wrapper to run prepare_repository in a separate process."""
    # Each process has its own event loop
    try:
        result = asyncio.run(_prepare_repository_async(repo, output_dir))
        return result
    except Exception as e:
        # Convert exception to serializable dict for multiprocessing
        error_msg = f"[prepare_repository] Error preparing {repo.remote}@{repo.commit}: {type(e).__name__}: {e}"
        print(error_msg)
        return {
            "snapshot_id": None,
            "remote": repo.remote,
            "commit": repo.commit,
            "stdout": "",
            "stderr": error_msg,
        }


def _process_single_sorry_sync(sorry: Sorry, strategy_name: str, strategy_args: dict, output_dir: Path) -> dict | None:
    """Synchronous wrapper to run process_single_sorry in a separate process."""
    # Each process has its own event loop
    try:
        result = asyncio.run(_process_single_sorry_async(sorry, strategy_name, strategy_args, output_dir))
        return result
    except Exception as e:
        # Convert exception to serializable dict for multiprocessing
        error_msg = f"[process_single_sorry] Error processing sorry {sorry.id}: {type(e).__name__}: {e}"
        print(error_msg)
        return {
            "sorry": sorry,
            "output_path": None,
            "error": {
                "type": type(e).__name__,
                "message": str(e),
            },
        }


async def _process_single_sorry_async(
    sorry: Sorry, strategy_name: str, strategy_args: dict, output_dir: Path
) -> dict | None:
    """Async function to process a single sorry on a MorphCloud instance."""
    log_path = _get_log_path("process_single_sorry", f"{sorry.id}.log", output_dir)

    with LogContext(log_path):
        print(f"[process_single_sorry] Starting for sorry {sorry.id}")

        mc = MorphCloudClient(api_key=MORPH_API_KEY)
        snap = await _prepare_repository_async(sorry.repo, output_dir)

        if snap["snapshot_id"] is None:
            print(f"[process_single_sorry] Failed to prepare repository for sorry {sorry.id}")
            return None

        print("[process_single_sorry] Starting instance...")
        with await mc.instances.astart(snapshot_id=snap["snapshot_id"]) as instance:
            print("[process_single_sorry] Running agent...")

            # Create .env file using aexec
            with open(find_dotenv(), "r") as f:
                env_content = f.read()
            create_env_cmd = f"cat > SorryDB/.env << 'EOF'\n{env_content}\nEOF"
            await instance.aexec(create_env_cmd)

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
            res = await instance.aexec(cmd)
            print(res.stdout, res.stderr)

            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{sorry.id}.json"
            instance.download("/root/repo/result.json", str(output_path))
            print(f"[process_single_sorry] Downloaded result to {output_path}")

        return {"sorry": sorry, "output_path": str(output_path)}


async def _prepare_repository_async(repo: RepoInfo, output_dir: Path | None = None) -> dict:
    """Async function to prepare a repository snapshot."""
    mc = MorphCloudClient(api_key=MORPH_API_KEY)
    repo_name = sanitize_repo_name(repo.remote)
    commit_short = (repo.commit or "unknown")[:12]
    log_path = _get_log_path("prepare_repository", f"{repo_name}_{commit_short}.log", output_dir)

    with LogContext(log_path) as ctx:
        print(f"[prepare_repository] Starting for {sanitize_repo_name(repo.remote)}")

        snap = await mc.snapshots.acreate(vcpus=4, memory=16384, disk_size=15000, digest="sorrydb-08-10-25")
        print(f"[prepare_repository] Snapshot created: {snap.id}")

        # Resolve the latest commit on the current branch to pin the build reproducibly
        sorrydb_branch_ref = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True
        ).strip()
        try:
            sorrydb_commit_ref = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip()
            print(f"[prepare_repository] Using current branch {sorrydb_branch_ref} at commit {sorrydb_commit_ref}")
        except Exception as e:
            sorrydb_commit_ref = sorrydb_branch_ref
            print(f"[prepare_repository] Warning: could not resolve commit: {e}")

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

        print("[prepare_repository] Running build steps...")
        try:
            result = await snap.abuild(steps=steps)  # type: ignore
            snapshot_id = result.id
            print(f"[prepare_repository] Build finished: {snapshot_id}")
        except Exception as e:
            snapshot_id = None
            print(f"[prepare_repository] Exception during build: {e}")
            print("NOTE: Make sure to have pushed your latest commit.")
        return {
            "snapshot_id": snapshot_id,
            "remote": repo.remote,
            "commit": repo.commit,
            "stdout": ctx.captured_stdout.getvalue() if ctx.captured_stdout else "",
            "stderr": ctx.captured_stderr.getvalue() if ctx.captured_stderr else "",
        }


def _filter_failed_sorries(sorries: list[Sorry], filter_path: Path) -> list[Sorry]:
    """Filter out sorries that are in filter.json."""
    if not filter_path.exists():
        return sorries

    with open(filter_path, "r") as f:
        filter_data = json.load(f)
        filtered_ids = {item["id"] for item in filter_data}

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


def _merge_sorries(output_dir: Path) -> list[SorryResult]:
    """Merge all individual sorry result files into a single list of SorryResult objects.

    Args:
        output_dir: Directory containing individual sorry result JSON files

    Returns:
        List of SorryResult objects from all processed sorries
    """
    results = []

    # Find all JSON files in the output directory
    json_files = list(output_dir.glob("*.json"))

    for json_file in json_files:
        # Skip the merged result file and failed file if they already exist
        if json_file.name in (FINAL_OUTPUT_NAME, FAILED_OUTPUT_NAME):
            continue

        try:
            with open(json_file, "r") as f:
                data = json.load(f)

            # Convert dict to SorryResult if needed
            if isinstance(data, dict):
                # Assume the file contains a SorryResult in dict form
                results.append(SorryResult(**data))
            elif isinstance(data, list):
                # If it's a list, add all items
                for item in data:
                    if isinstance(item, dict):
                        results.append(SorryResult(**item))
        except Exception as e:
            print(f"Error reading {json_file}: {e}")
            continue

    return results


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

    def _prepare_sorries(self, sorry_list: list[Sorry], output_dir: Path) -> tuple[list[Sorry], list[Sorry]]:
        """Prepare repository snapshots using multiprocessing for parallel execution."""
        # Get unique (remote, commit) pairs
        remote_commit_pairs = {(s.repo.remote, s.repo.commit): s.repo for s in sorry_list}
        repos = list(remote_commit_pairs.values())

        # Create partial function with output_dir
        prepare_func = partial(_prepare_repository_sync, output_dir=output_dir)

        # Use ProcessPoolExecutor for true parallel execution
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            results = list(executor.map(prepare_func, repos))

        # Separate Sorrys into successful and failed preparations
        prepared_sorries = []
        failed_sorries = []
        for result in results:
            if result["snapshot_id"] is not None:
                for s in sorry_list:
                    if s.repo.remote == result["remote"] and s.repo.commit == result["commit"]:
                        prepared_sorries.append(s)
            else:
                for s in sorry_list:
                    if s.repo.remote == result["remote"] and s.repo.commit == result["commit"]:
                        failed_sorries.append(s)
        return prepared_sorries, failed_sorries

    def _process_sorries(self, sorries: list[Sorry], output_dir: Path) -> list[dict | None]:
        """Process multiple sorries in parallel using multiprocessing."""
        # Create partial function with strategy parameters
        process_func = partial(
            _process_single_sorry_sync,
            strategy_name=self.strategy_name,
            strategy_args=self.strategy_args,
            output_dir=output_dir,
        )

        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            results = list(executor.map(process_func, sorries))

        return results

    def process_sorries(self, sorry_json_path: Path, output_dir: Path):
        """Process sorries from a JSON file and save results to output directory.

        Sorries whose repos fail to build are logged in FAILED_OUTPUT_NAME (failed.json)
        in the output directory. To avoid retrying failed sorries, place failed.json
        in the same directory as the output folder.

        Args:
            sorry_json_path: Path to JSON file containing sorries
            output_dir: Directory to save results
        """
        # Load sorries
        sorries = load_sorry_json(sorry_json_path)
        print(f"Loaded {len(sorries)} sorries from {sorry_json_path}")

        # Filter out sorries in FAILED_OUTPUT_NAME
        filter_path = output_dir / FAILED_OUTPUT_NAME
        sorries = _filter_failed_sorries(sorries, filter_path)

        # Validate GitHub commits
        sorries = _validate_github_commits(sorries)
        print(f"Validated {len(sorries)} sorries")

        # Prepare repository snapshots
        print("Preparing repository snapshots...")
        sorries, failed_sorries = self._prepare_sorries(sorries, output_dir)
        print(f"Prepared {len(sorries)} sorries")

        # Save failed sorries
        if failed_sorries:
            print(f"Failed to build {len(failed_sorries)} repos")
            failed_path = output_dir / FAILED_OUTPUT_NAME
            with open(failed_path, "w") as f:
                json.dump(failed_sorries, f, indent=4, cls=SorryJSONEncoder)
            print(f"Failed sorries saved to {failed_path}")

        # Process sorries
        print("Processing sorries on MorphCloud...")
        results = self._process_sorries(sorries, output_dir)

        # Merge all individual results into a single file
        print("Merging results...")
        merged_results = _merge_sorries(output_dir)
        result_path = output_dir / FINAL_OUTPUT_NAME
        with open(result_path, "w") as f:
            json.dump(merged_results, f, indent=4, cls=SorryJSONEncoder)
        print(f"Merged results saved to {result_path}")

        # Finish
        print(f"Processed {len(results)} sorries")
        print(f"Results saved to {output_dir}")
        return results


if __name__ == "__main__":
    # Example usage
    agent = MorphCloudAgent(strategy_name="rfl", strategy_args={}, max_workers=4)

    # Process from local file
    sorry_file = Path("mock_sorry.json")
    output_dir = Path("outputs")
    agent.process_sorries(sorry_file, output_dir)
