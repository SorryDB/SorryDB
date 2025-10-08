import asyncio
import json
import os
import logging
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()
MORPH_API_KEY = os.environ["MORPH_API_KEY"]

from morphcloud.api import MorphCloudClient

from ..agents.json_agent import load_sorry_json
from ..database.sorry import RepoInfo, Sorry, SorryJSONEncoder


def _sanitize_repo_name(remote: str) -> str:
    """Return a safe repository name from a remote URL/SSH string."""
    name = remote.rstrip("/")
    if name.endswith(".git"):
        name = name[:-4]
    name = name.split("/")[-1]
    name = name.split(":")[-1]
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "-" for c in name)


def _get_log_path(repo: RepoInfo) -> Path:
    logs_root = Path(__file__).resolve().parents[2] / "logs" / "prepare_repository"
    logs_root.mkdir(parents=True, exist_ok=True)
    repo_name = _sanitize_repo_name(repo.remote)
    commit_short = (repo.commit or "unknown")[:12]
    return logs_root / f"{repo_name}_{commit_short}.log"


def prepare_repository_sync(repo: RepoInfo) -> dict:
    """Synchronous wrapper to run prepare_repository in a separate process."""
    # Each process has its own event loop
    result = asyncio.run(_prepare_repository_async(repo))
    return result


async def _prepare_repository_async(repo: RepoInfo) -> dict:
    """Async function to prepare a repository snapshot."""
    import sys
    from io import StringIO

    mc = MorphCloudClient(api_key=MORPH_API_KEY)
    log_path = _get_log_path(repo)

    # Each process writes to its own log file and captures stdout/stderr
    with open(log_path, "w", encoding="utf-8") as log_file:

        def log(msg: str):
            print(msg)
            log_file.write(msg + "\n")
            log_file.flush()

        log(f"[prepare_repository] Starting for {_sanitize_repo_name(repo.remote)}")

        snap = await mc.snapshots.acreate(vcpus=4, memory=16384, disk_size=15000, digest="sorrydb-08-10-25")
        log(f"[prepare_repository] Snapshot created: {snap.id}")

        steps = [
            (
                "apt-get update && apt-get install -y curl git wget htop gnupg python3 python3-pip python3-venv python-is-python3 pipx python3-dev"
                " && curl https://elan.lean-lang.org/elan-init.sh -sSf | sh -s -- -y --default-toolchain leanprover/lean4:v4.21.0"
                " && pipx install poetry"
            ),
            (
                'git clone https://github.com/SorryDB/SorryDB.git && cd SorryDB && export PATH="$HOME/.local/bin:$PATH"'
                " && poetry install"
            ),
            (
                f"git clone {repo.remote} repo && cd repo && git checkout {repo.commit}"
                f' && export PATH="$HOME/.elan/bin:$PATH" && (lake exe cache get || true) && lake build'
            ),
        ]

        log("[prepare_repository] Running build steps...")

        # Capture stdout and stderr during abuild
        old_stdout, old_stderr = sys.stdout, sys.stderr
        captured_stdout = StringIO()
        captured_stderr = StringIO()

        class Tee:
            def __init__(self, *outputs):
                self.outputs = outputs

            def write(self, data):
                for output in self.outputs:
                    output.write(data)
                return len(data)

            def flush(self):
                for output in self.outputs:
                    output.flush()

        try:
            # Tee stdout/stderr to both original streams, log file, and capture buffers
            sys.stdout = Tee(old_stdout, log_file, captured_stdout)
            sys.stderr = Tee(old_stderr, log_file, captured_stderr)

            result = await snap.abuild(steps=steps)  # type: ignore
        except Exception as e:
            log(f"[prepare_repository] Exception during build: {e}")
            return {
                "snapshot_id": None,
                "remote": repo.remote,
                "commit": repo.commit,
                "stdout": captured_stdout.getvalue(),
                "stderr": captured_stderr.getvalue(),
            }
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        log(f"[prepare_repository] Build finished: {result.id}")

        return {
            "snapshot_id": result.id,
            "remote": repo.remote,
            "commit": repo.commit,
            "stdout": captured_stdout.getvalue(),
            "stderr": captured_stderr.getvalue(),
        }


def _parse_remote(remote: str) -> tuple[str | None, str | None, str | None]:
    """Returns (host, owner, repo) when determinable, else (host, None, None)"""
    if remote.startswith("git@"):
        try:
            after_at = remote.split("@", 1)[1]
            host, path = after_at.split(":", 1)
            path = path.rstrip("/")
            if path.endswith(".git"):
                path = path[:-4]
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 2:
                return host, parts[0], parts[1]
            return host, None, None
        except Exception:
            return None, None, None
    else:
        try:
            u = urlparse(remote)
            host = u.netloc
            path = u.path.rstrip("/")
            if path.endswith(".git"):
                path = path[:-4]
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 2:
                return host, parts[0], parts[1]
            return host or None, None, None
        except Exception:
            return None, None, None


def _github_commit_exists(owner: str, repo: str, ref: str) -> tuple[bool, str]:
    """Check if a commit exists on GitHub."""
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{ref}"
    try:
        headers = {"Accept": "application/vnd.github+json"}
        token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        r = requests.get(url, timeout=15, headers=headers)
        if r.status_code == 200:
            return True, "ok"
        if r.status_code == 404:
            repo_url = f"https://api.github.com/repos/{owner}/{repo}"
            r2 = requests.get(repo_url, timeout=15, headers=headers)
            if r2.status_code == 404:
                return False, "repository not found"
            return False, "commit not found"
        return False, f"github api status {r.status_code}"
    except Exception as e:
        return False, f"github api error: {e}"


def get_sorry_list(sorry_url: str) -> list[Sorry]:
    """Download and validate sorry list from URL."""
    SORRY_PATH = Path(__file__).parent.parent.parent / "mock_sorry.json"
    response = requests.get(sorry_url, timeout=30)
    response.raise_for_status()
    with open(SORRY_PATH, "wb") as file:
        file.write(response.content)

    sorries = load_sorry_json(Path(SORRY_PATH))

    # Validate GitHub commits
    valid_cache: dict[tuple[str, str], tuple[bool, str]] = {}
    for s in sorries:
        pair = (s.repo.remote, s.repo.commit)
        if pair in valid_cache:
            continue
        host, owner, repo = _parse_remote(s.repo.remote)
        if host == "github.com" and owner and repo:
            ok, reason = _github_commit_exists(owner, repo, s.repo.commit)
        else:
            ok, reason = True, "skipped-non-github"
        valid_cache[pair] = (ok, reason)

    filtered: list[Sorry] = []
    for s in sorries:
        ok, reason = valid_cache[(s.repo.remote, s.repo.commit)]
        if not ok:
            print(f"[get_sorry_list] Skipping invalid repo/commit: {s.repo.remote}@{s.repo.commit} -> {reason}")
            continue
        filtered.append(s)
    return filtered


def prepare_sorries(sorry_list: list[Sorry], max_workers: int = 4) -> list[Sorry]:
    """Prepare repositories using multiprocessing for parallel execution."""
    # Get unique (remote, commit) pairs
    remote_commit_pairs = {(s.repo.remote, s.repo.commit): s.repo for s in sorry_list}
    repos = list(remote_commit_pairs.values())

    # Use ProcessPoolExecutor for true parallel execution
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(prepare_repository_sync, repos))

    # Return only Sorrys with successful preparations
    prepared_sorries = []
    for result in results:
        if result["snapshot_id"] is not None:
            for s in sorry_list:
                if s.repo.remote == result["remote"] and s.repo.commit == result["commit"]:
                    prepared_sorries.append(s)
    return prepared_sorries


async def run_agent(sorry: Sorry, agent_name: str = "rfl", agent_args: dict = {}, sem: asyncio.Semaphore | None = None):
    async with sem or asyncio.Semaphore():
        mc = MorphCloudClient(api_key=MORPH_API_KEY)
        snap = await _prepare_repository_async(sorry.repo)

        # Read .env file content
        env_path = Path(__file__).parent.parent.parent / ".env"
        with open(env_path, "r") as f:
            env_content = f.read()

        print("Starting instances...")
        with await mc.instances.astart(snapshot_id=snap["snapshot_id"]) as instance:
            print("Running agent..")

            # Create .env file using aexec
            create_env_cmd = f"cat > SorryDB/.env << 'EOF'\n{env_content}\nEOF"
            print(await instance.aexec(create_env_cmd))

            cmd = f'cd SorryDB && export PATH="$HOME/.local/bin:$PATH" && export PATH="$HOME/.elan/bin:$PATH" && git pull && git checkout dev/morphcloud && poetry install && eval $(poetry env activate) && poetry run python -m sorrydb.agents.run_single_agent --repo-path repo --sorry-json \'{json.dumps(sorry, cls=SorryJSONEncoder)}\' --agent-strategy \'{{"name": "{agent_name}", "args": {json.dumps(agent_args)}}}\''
            print(await instance.aexec(cmd))

            os.makedirs("outputs", exist_ok=True)
            output_path = f"outputs/{sorry.id}"
            instance.download("repo/result.json", output_path)
            print(f"Downloaded result in {output_path}")
        return output_path


async def run_agent_batch(sorries: list[Sorry], agent_name: str = "rfl", agent_args: dict = {}, batch_size: int = 4):
    sem = asyncio.Semaphore(batch_size)
    paths = await asyncio.gather(
        *[run_agent(sorry, agent_name, agent_args, sem) for sorry in sorries],
        return_exceptions=True,
    )
    print(paths)
    return paths


if __name__ == "__main__":
    SORRY_URL = "https://raw.githubusercontent.com/SorryDB/sorrydb-data/refs/heads/master/static_100_varied_recent_deduplicated_sorries.json"
    print("Getting sorry list from", SORRY_URL)
    sorries = get_sorry_list(SORRY_URL)
    sorries = sorries[4:14]
    print(f"Loaded {len(sorries)} sorries")

    print("Preparing repositories...")
    sorries = prepare_sorries(sorries, max_workers=4)

    print("Running agents...")
    asyncio.run(run_agent_batch(sorries=sorries, agent_name="rfl", agent_args={}, batch_size=4))
