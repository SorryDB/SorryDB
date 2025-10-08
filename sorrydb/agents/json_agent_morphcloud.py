import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from morphcloud.api import MorphCloudClient, Snapshot

from ..agents.json_agent import load_sorry_json
from ..database.sorry import RepoInfo, Sorry, SorryJSONEncoder

load_dotenv()
MORPH_API_KEY = os.environ["MORPH_API_KEY"]

# Create a module-level logger
logger = logging.getLogger(__name__)


# --- Logging utilities ---
def _sanitize_repo_name(remote: str) -> str:
    """Return a safe repository name from a remote URL/SSH string."""
    name = remote.rstrip("/")
    if name.endswith(".git"):
        name = name[:-4]
    # Handle both HTTPS and SSH style URLs
    name = name.split("/")[-1]
    name = name.split(":")[-1]
    # Replace any remaining unsafe characters
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "-" for c in name)


def _get_log_path(repo: RepoInfo) -> Path:
    logs_root = Path(__file__).resolve().parents[2] / "logs" / "prepare_repository"
    logs_root.mkdir(parents=True, exist_ok=True)
    repo_name = _sanitize_repo_name(repo.remote)
    commit_short = (repo.commit or "unknown")[:12]
    return logs_root / f"{repo_name}_{commit_short}.log"


class _Tee:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, s):
        for st in self._streams:
            try:
                st.write(s)
                st.flush()
            except Exception:
                pass
        return len(s)

    def flush(self):
        for st in self._streams:
            try:
                st.flush()
            except Exception:
                pass


class _CapturePrints:
    """Context manager that tees stdout and stderr into a file."""

    def __init__(self, file_path: Path, tee: bool = True):
        self.file_path = file_path
        self.tee = tee
        self._orig_out = None
        self._orig_err = None
        self._file = None

    def __enter__(self):
        self._orig_out, self._orig_err = sys.stdout, sys.stderr
        self._file = open(self.file_path, "a", encoding="utf-8")
        if self.tee:
            sys.stdout = _Tee(self._orig_out, self._file)  # type: ignore[assignment]
            sys.stderr = _Tee(self._orig_err, self._file)  # type: ignore[assignment]
        else:
            sys.stdout = self._file  # type: ignore[assignment]
            sys.stderr = self._file  # type: ignore[assignment]
        return self

    def __exit__(self, exc_type, exc, tb):
        sys.stdout, sys.stderr = self._orig_out, self._orig_err
        if self._file:
            try:
                self._file.flush()
            finally:
                self._file.close()
        # Do not suppress exceptions
        return False


async def prepare_repository(repo: RepoInfo, sem: asyncio.Semaphore | None = None) -> Snapshot:
    async with sem or asyncio.Semaphore():
        mc = MorphCloudClient(api_key=MORPH_API_KEY)
        log_path = _get_log_path(repo)
        with _CapturePrints(log_path, tee=True):
            print("[prepare_repository] starting")
            snap = await mc.snapshots.acreate(vcpus=4, memory=16384, disk_size=15000, digest="sorrydb-08-10-25")
            print(f"[prepare_repository] snapshot created id={getattr(snap, 'id', 'unknown')}")
            steps = []

            # OS deps
            steps.append(
                "apt-get update && apt-get install -y curl git wget htop gnupg python3 python3-pip python3-venv python-is-python3 pipx python3-dev"
                " && curl https://elan.lean-lang.org/elan-init.sh -sSf | sh -s -- -y --default-toolchain leanprover/lean4:v4.21.0"
                " && pipx install poetry"
            )

            # Clone and build repo
            steps.append(
                'git clone https://github.com/SorryDB/SorryDB.git && cd SorryDB && export PATH="$HOME/.local/bin:$PATH"'
                " && poetry install"
            )

            steps.append(
                f'git clone {repo.remote} repo && cd repo && git checkout {repo.commit} && export PATH="$HOME/.elan/bin:$PATH" && (lake exe cache get || true) && lake build'
            )

            print("[prepare_repository] build steps prepared:")
            for s in steps:
                print("  -", s)

            result = await snap.abuild(steps=steps)
            print("[prepare_repository] build finished")
            try:
                print("[prepare_repository] result:", json.dumps(result, default=str))  # type: ignore[arg-type]
            except Exception:
                print("[prepare_repository] result:", result)
            return result


def get_sorry_list(sorry_url: str) -> list[Sorry]:
    SORRY_PATH = Path(__file__).parent.parent.parent / "mock_sorry.json"
    response = requests.get(sorry_url, timeout=30)
    response.raise_for_status()
    with open(SORRY_PATH, "wb") as file:
        file.write(response.content)

    sorries = load_sorry_json(Path(SORRY_PATH))

    # Deduplicate (remote, commit) checks
    def _parse_remote(remote: str):
        # Returns (host, owner, repo) when determinable, else (host, None, None)
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
        # Use the commits/{ref} endpoint which accepts SHAs, branches, and tags
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
                # Check if repo exists at all
                repo_url = f"https://api.github.com/repos/{owner}/{repo}"
                r2 = requests.get(repo_url, timeout=15, headers=headers)
                if r2.status_code == 404:
                    return False, "repository not found"
                return False, "commit not found"
            return False, f"github api status {r.status_code}"
        except Exception as e:
            return False, f"github api error: {e}"

    valid_cache: dict[tuple[str, str], tuple[bool, str]] = {}
    for s in sorries:
        pair = (s.repo.remote, s.repo.commit)
        if pair in valid_cache:
            continue
        host, owner, repo = _parse_remote(s.repo.remote)
        ok = False
        reason = ""
        if host == "github.com" and owner and repo:
            ok, reason = _github_commit_exists(owner, repo, s.repo.commit)
        else:
            # Only API check requested; skip validation for non-GitHub remotes
            ok, reason = True, "skipped-non-github"
        valid_cache[pair] = (ok, reason)

    filtered: list[Sorry] = []
    for s in sorries:
        ok, reason = valid_cache[(s.repo.remote, s.repo.commit)]
        if not ok:
            print(
                f"[get_sorry_list] Skipping invalid repo/commit: {s.repo.remote}@{s.repo.commit} -> {reason}",
                file=sys.stderr,
            )
            continue
        filtered.append(s)
    return filtered


async def prepare_sorries(sorry_list: list[Sorry], batch_size: int = 16):
    remote_commit_pair_set = {(s.repo.remote, s.repo.commit): s.repo for s in sorry_list}
    # build snapshots for each unique (remote, commit) pair
    sem = asyncio.Semaphore(batch_size)
    await asyncio.gather(*[prepare_repository(repo, sem) for _, repo in list(remote_commit_pair_set.items())])


async def run_agent(sorry: Sorry, agent_name: str = "rfl", agent_args: dict = {}, sem: asyncio.Semaphore | None = None):
    async with sem or asyncio.Semaphore():
        mc = MorphCloudClient(api_key=MORPH_API_KEY)
        snap = await prepare_repository(sorry.repo)

        # Read .env file content
        env_path = Path(__file__).parent.parent.parent / ".env"
        with open(env_path, "r") as f:
            env_content = f.read()

        print("Starting instances...")
        with await mc.instances.astart(snapshot_id=snap.id) as instance:
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


async def run_agent_batch(sorries: list[Sorry], agent_name: str = "rfl", agent_args: dict = {}):
    sem = asyncio.Semaphore(4)
    paths = await asyncio.gather(
        *[run_agent(sorry, agent_name, agent_args, sem) for sorry in sorries],
        return_exceptions=True,
    )
    print(paths)
    return paths


if __name__ == "__main__":
    SORRY_URL = "https://raw.githubusercontent.com/SorryDB/sorrydb-data/refs/heads/master/static_100_varied_recent_deduplicated_sorries.json"
    sorries = get_sorry_list(SORRY_URL)
    sorries = sorries[4:14]
    asyncio.run(prepare_sorries(sorries))
    asyncio.run(run_agent_batch(sorries=sorries, agent_name="rfl"))
