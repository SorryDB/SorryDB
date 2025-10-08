import asyncio
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from morphcloud.api import MorphCloudClient

from ..agents.json_agent import load_sorry_json
from ..database.sorry import RepoInfo, Sorry, SorryJSONEncoder
from ..utils.git_ops import github_commit_exists, parse_remote, sanitize_repo_name
from ..utils.logging import LogContext

load_dotenv()
MORPH_API_KEY = os.environ["MORPH_API_KEY"]


def _get_log_path(subdirectory: str, filename: str) -> Path:
    logs_root = Path(__file__).resolve().parents[2] / "logs" / subdirectory
    logs_root.mkdir(parents=True, exist_ok=True)
    return logs_root / filename


def _prepare_repository_sync(repo: RepoInfo) -> dict:
    """Synchronous wrapper to run prepare_repository in a separate process."""
    # Each process has its own event loop
    result = asyncio.run(_prepare_repository_async(repo))
    return result


async def _prepare_repository_async(repo: RepoInfo) -> dict:
    """Async function to prepare a repository snapshot."""
    mc = MorphCloudClient(api_key=MORPH_API_KEY)
    repo_name = sanitize_repo_name(repo.remote)
    commit_short = (repo.commit or "unknown")[:12]
    log_path = _get_log_path("prepare_repository", f"{repo_name}_{commit_short}.log")

    with LogContext(log_path) as ctx:
        print(f"[prepare_repository] Starting for {sanitize_repo_name(repo.remote)}")

        snap = await mc.snapshots.acreate(
            vcpus=4, memory=16384, disk_size=15000, digest="sorrydb-08-10-25"
        )
        print(f"[prepare_repository] Snapshot created: {snap.id}")

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
        ]

        print("[prepare_repository] Running build steps...")
        try:
            result = await snap.abuild(steps=steps)  # type: ignore
            snapshot_id = result.id
            print(f"[prepare_repository] Build finished: {snapshot_id}")
        except Exception as e:
            snapshot_id = None
            print(f"[prepare_repository] Exception during build: {e}")

        return {
            "snapshot_id": snapshot_id,
            "remote": repo.remote,
            "commit": repo.commit,
            "stdout": ctx.captured_stdout.getvalue(),
            "stderr": ctx.captured_stderr.getvalue(),
        }


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
            print(
                f"[validate_commits] Skipping invalid repo/commit: {s.repo.remote}@{s.repo.commit} -> {reason}"
            )
            continue
        filtered.append(s)
    return filtered


class MorphCloudAgent:
    """
    MorphCloudAgent runs a SorryStrategy on remote MorphCloud instances.

    Similar to JsonAgent but executes on cloud infrastructure:
    - Prepares repositories as snapshots on MorphCloud
    - Spawns instances from snapshots in parallel
    - Runs strategies remotely and downloads results

    Args:
        strategy_name: Name of the strategy to use (e.g., "rfl", "agentic")
        strategy_args: Arguments to pass to the strategy
        batch_size: Maximum number of concurrent instances
        max_workers: Maximum number of workers for repository preparation
    """

    def __init__(
        self,
        strategy_name: str = "rfl",
        strategy_args: dict | None = None,
        batch_size: int = 4,
        max_workers: int = 4,
    ):
        self.strategy_name = strategy_name
        self.strategy_args = strategy_args or {}
        self.batch_size = batch_size
        self.max_workers = max_workers

    def _prepare_sorries(self, sorry_list: list[Sorry]) -> list[Sorry]:
        """Prepare repository snapshots using multiprocessing for parallel execution."""
        # Get unique (remote, commit) pairs
        remote_commit_pairs = {
            (s.repo.remote, s.repo.commit): s.repo for s in sorry_list
        }
        repos = list(remote_commit_pairs.values())

        # Use ProcessPoolExecutor for true parallel execution
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            results = list(executor.map(_prepare_repository_sync, repos))

        # Return only Sorrys with successful preparations
        prepared_sorries = []
        for result in results:
            if result["snapshot_id"] is not None:
                for s in sorry_list:
                    if (
                        s.repo.remote == result["remote"]
                        and s.repo.commit == result["commit"]
                    ):
                        prepared_sorries.append(s)
        return prepared_sorries

    async def _process_single_sorry(
        self, sorry: Sorry, sem: asyncio.Semaphore
    ) -> dict | None:
        """Process a single sorry on a MorphCloud instance."""
        async with sem:
            log_path = _get_log_path("process_single_sorry", f"{sorry.id}.log")

            with LogContext(log_path):
                print(f"[process_single_sorry] Starting for sorry {sorry.id}")

                mc = MorphCloudClient(api_key=MORPH_API_KEY)
                snap = await _prepare_repository_async(sorry.repo)

                if snap["snapshot_id"] is None:
                    print(
                        f"[process_single_sorry] Failed to prepare repository for sorry {sorry.id}"
                    )
                    return None

                print("[process_single_sorry] Starting instance...")
                with await mc.instances.astart(
                    snapshot_id=snap["snapshot_id"]
                ) as instance:
                    print("[process_single_sorry] Running agent...")

                    # Create .env file using aexec
                    with open(find_dotenv(), "r") as f:
                        env_content = f.read()
                    create_env_cmd = f"cat > SorryDB/.env << 'EOF'\n{env_content}\nEOF"
                    await instance.aexec(create_env_cmd)

                    cmd = (
                        f"cd SorryDB && "
                        f'export PATH="$HOME/.local/bin:$PATH" && '
                        f'export PATH="$HOME/.elan/bin:$PATH" && '
                        f"git pull && "
                        f"git checkout dev/morphcloud && "
                        f"poetry install && "
                        f"eval $(poetry env activate) && "
                        f"poetry run python -m sorrydb.cli.run_morphcloud_local "
                        f"--repo-path ~/repo "
                        f"--sorry-json '{json.dumps(sorry, cls=SorryJSONEncoder)}' "
                        f'--agent-strategy \'{{"name": "{self.strategy_name}", "args": {json.dumps(self.strategy_args)}}}\''
                    )
                    res = await instance.aexec(cmd)
                    print(res.stdout, res.stderr)

                    os.makedirs("outputs", exist_ok=True)
                    output_path = f"outputs/{sorry.id}.json"
                    instance.download("/root/repo/result.json", output_path)
                    print(f"[process_single_sorry] Downloaded result to {output_path}")

                return {"sorry": sorry, "output_path": output_path}

    async def _process_sorries(self, sorries: list[Sorry]) -> list[dict | None]:
        """Process multiple sorries in parallel with semaphore control."""
        sem = asyncio.Semaphore(self.batch_size)
        results = await asyncio.gather(
            *[self._process_single_sorry(sorry, sem) for sorry in sorries],
            return_exceptions=True,
        )
        return results

    def process_sorries(self, sorry_json_path: Path, output_dir: Path):
        """Process sorries from a JSON file and save results to output directory.

        Args:
            sorry_json_path: Path to JSON file containing sorries
            output_dir: Directory to save results
        """
        # Load sorries
        sorries = load_sorry_json(sorry_json_path)
        print(f"Loaded {len(sorries)} sorries from {sorry_json_path}")

        # Validate GitHub commits
        sorries = _validate_github_commits(sorries)
        print(f"Validated {len(sorries)} sorries")

        # Prepare repository snapshots
        print("Preparing repository snapshots...")
        sorries = self._prepare_sorries(sorries)
        print(f"Prepared {len(sorries)} sorries")

        # Process sorries
        print("Processing sorries on MorphCloud...")
        results = asyncio.run(self._process_sorries(sorries))

        # Save results
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Results saved to {output_dir}")
        print(f"Processed {len(results)} sorries")

        return results


if __name__ == "__main__":
    # Example usage
    agent = MorphCloudAgent(
        strategy_name="rfl", strategy_args={}, batch_size=4, max_workers=4
    )

    # Process from local file
    sorry_file = Path("mock_sorry.json")
    output_dir = Path("outputs")
    agent.process_sorries(sorry_file, output_dir)
