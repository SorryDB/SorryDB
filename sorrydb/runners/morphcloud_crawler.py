"""Crawl-side MorphCloud runner.

Follows the two-phase pattern of morphcloud_runner: first build a snapshot in
which the target repository is already cloned and compiled, then start an
instance from that snapshot just long enough to run the extraction entrypoint
and download the resulting JSON.

`morphcloud_extractor` matches the extractor protocol of
sorrydb.database.build_database, so `update_database` can build every repo on a
fresh VM instead of on the machine running the crawl.
"""

import asyncio
import json
import shlex
import tempfile
import time
from pathlib import Path

from git import Repo
from morphcloud.api import MorphCloudClient

from ..utils.git_ops import sanitize_repo_name
from ..utils.logging import setup_logger
from .morphcloud_runner import (
    BUILD_TIMEOUT,
    FILE_OP_TIMEOUT,
    MAX_BUILD_RETRIES,
    MORPH_API_KEY,
    _create_cache_retry_step,
    _get_log_path,
)

# Own digest, so crawler snapshots do not collide with the agent runner's.
CRAWLER_DIGEST = "sorrydb-crawler-09-01-26"
# prepare_repository checks out into <LEAN_DATA>/<repo name>, so the build steps
# put the prebuilt clone exactly where the extraction entrypoint looks for it.
LEAN_DATA = "/root/lean_data"
REMOTE_OUTPUT = "/root/extract_result.json"
EXTRACT_TIMEOUT = 3600
# SorryDB commit with frozen package deps, so `poetry install` stays cached
FROZEN_DEPS_COMMIT = "7e6991be03405cfb334a91a67b63a2e1ee550fbe"


def _checkout_dir_name(repo_url: str) -> str:
    """Directory name prepare_repository derives from a remote URL."""
    name = repo_url.rstrip("/").split("/")[-1]
    return name[:-4] if name.endswith(".git") else name


def _build_steps(repo_url: str, commit_sha: str, sorrydb_commit: str) -> list:
    """Build steps for one (repo, commit).

    Steps 1 to 3 are byte-identical for every repo of a run, so Morph reuses the
    cached prefix and only the per-repo steps actually run.
    """
    checkout = f"{LEAN_DATA}/{_checkout_dir_name(repo_url)}"
    return [
        # Step 1: system dependencies and toolchain
        (
            "("
            "apt-get update && "
            "apt-get install -y curl git wget htop gnupg python3 python3-pip python3-venv python-is-python3 pipx python3-dev && "
            "curl https://elan.lean-lang.org/elan-init.sh -sSf | sh -s -- -y --default-toolchain leanprover/lean4:v4.21.0 && "
            "pipx install poetry"
            ") > /tmp/step_1.log 2>&1"
        ),
        # Step 2: clone SorryDB at the frozen-deps commit and install its deps
        (
            "("
            "git clone https://github.com/SorryDB/SorryDB.git && "
            "cd SorryDB && "
            f"git checkout {FROZEN_DEPS_COMMIT} && "
            'export PATH="$HOME/.local/bin:$PATH" && '
            "poetry install"
            ") > /tmp/step_2.log 2>&1"
        ),
        # Step 3: move SorryDB to the commit we are running
        (
            "("
            "cd SorryDB && "
            'export PATH="$HOME/.local/bin:$PATH" && '
            "git fetch && "
            f"git checkout {sorrydb_commit} && "
            "poetry install"
            ") > /tmp/step_3.log 2>&1"
        ),
        # Step 4a: clone the target repo where prepare_repository expects it, and
        # symlink it to ~/repo, which the shared cache step operates on
        (
            "("
            f"mkdir -p {LEAN_DATA} && "
            f"git clone {shlex.quote(repo_url)} {checkout} && "
            f"ln -sfn {checkout} /root/repo && "
            "cd /root/repo && "
            f"(git fetch origin {commit_sha} || true) && "
            f"git checkout {commit_sha}"
            ") > /tmp/step_4a.log 2>&1"
        ),
        # Step 4b: get lake cache with retry (callable)
        _create_cache_retry_step(),
        # Step 4c: build the target repo
        (
            "("
            "cd /root/repo && "
            'export PATH="$HOME/.elan/bin:$PATH" && '
            "lake build"
            ") > /tmp/step_4c.log 2>&1"
        ),
    ]


async def _build_snapshot(
    mc: MorphCloudClient, repo_url: str, commit_sha: str, logger
) -> str:
    """Build a snapshot with the target repo already compiled. Returns its id."""
    snapshot_name = f"{sanitize_repo_name(repo_url)}_{commit_sha[:12]}"
    logger.info(f"Creating snapshot {snapshot_name}")
    snap = await mc.snapshots.acreate(
        vcpus=4,
        memory=16384,
        disk_size=25000,
        digest=CRAWLER_DIGEST,
        metadata={"name": snapshot_name, "repo": repo_url, "commit": commit_sha},
    )

    steps = _build_steps(repo_url, commit_sha, Repo(".").head.commit.hexsha)

    for attempt in range(1, MAX_BUILD_RETRIES + 1):
        build_start = time.time()
        try:
            logger.info(f"Build attempt {attempt}/{MAX_BUILD_RETRIES} on {snap.id}")
            built = await asyncio.wait_for(
                snap.abuild(steps=steps),  # type: ignore
                timeout=BUILD_TIMEOUT,
            )
            logger.info(
                f"Build finished: {built.id} (duration: {time.time() - build_start:.1f}s)"
            )
            return built.id
        except asyncio.TimeoutError:
            logger.warning(
                f"Build timed out after {BUILD_TIMEOUT}s "
                f"(attempt {attempt}/{MAX_BUILD_RETRIES})"
            )
            if attempt == MAX_BUILD_RETRIES:
                raise
            logger.info("Retrying, cached steps will be reused automatically")

    raise RuntimeError("unreachable")


async def _extract_async(repo_url: str, branch: str, commit_sha: str, logger) -> dict:
    mc = MorphCloudClient(api_key=MORPH_API_KEY)
    snapshot_id = await _build_snapshot(mc, repo_url, commit_sha, logger)

    cmd = (
        "cd SorryDB && "
        'export PATH="$HOME/.local/bin:$PATH" && '
        'export PATH="$HOME/.elan/bin:$PATH" && '
        "poetry run python -m sorrydb.cli.run_morphcloud_extract "
        f"--repo-url {shlex.quote(repo_url)} "
        f"--branch {shlex.quote(branch)} "
        f"--commit {shlex.quote(commit_sha)} "
        f"--lean-data {LEAN_DATA} "
        f"--output-path {REMOTE_OUTPUT}"
    )

    logger.info(f"Starting instance from {snapshot_id}")
    # The post-extraction state is deliberately not snapshotted: the instance is
    # stopped when this context exits.
    with await mc.instances.astart(
        snapshot_id=snapshot_id,
        ttl_seconds=EXTRACT_TIMEOUT + 120,
        timeout=EXTRACT_TIMEOUT + 60,
        metadata={"name": f"crawl_{sanitize_repo_name(repo_url)}_{commit_sha[:12]}"},
    ) as instance:
        logger.info(f"Instance started: {instance.id}, running extraction")
        result = await instance.aexec(cmd, EXTRACT_TIMEOUT)
        logger.info(f"Extraction finished (exit_code: {result.exit_code})")
        logger.info(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            logger.info(f"STDERR:\n{result.stderr}")

        if result.exit_code != 0:
            raise RuntimeError(
                f"Extraction of {repo_url}@{commit_sha} failed with "
                f"exit code {result.exit_code}"
            )

        with tempfile.TemporaryDirectory() as download_dir:
            local_path = Path(download_dir) / "extract_result.json"
            await asyncio.wait_for(
                instance.adownload(REMOTE_OUTPUT, str(local_path)),
                timeout=FILE_OP_TIMEOUT,
            )
            with open(local_path, "r", encoding="utf-8") as f:
                return json.load(f)


def morphcloud_extractor(
    repo_url: str, branch: str, commit_sha: str, lean_data: Path
) -> dict:
    """Extract sorries by building the repository on a fresh MorphCloud VM.

    Matches the extractor protocol of sorrydb.database.build_database.
    `lean_data` is unused: nothing is built on this machine.

    Raises on failure, which process_new_commits logs before moving on to the
    next commit, so one bad repo never aborts the crawl.
    """
    label = f"{sanitize_repo_name(repo_url)}_{commit_sha[:12]}"
    log_path = _get_log_path("morphcloud_crawl", f"{label}.log")

    with setup_logger(f"morphcloud_crawl_{label}", log_path) as logger:
        logger.info(f"Extracting {repo_url}@{commit_sha} on branch {branch}")
        print(f"[crawl] Building {repo_url}@{commit_sha[:12]} on MorphCloud")
        results = asyncio.run(_extract_async(repo_url, branch, commit_sha, logger))
        logger.info(f"Extracted {len(results['sorries'])} sorries")
        print(f"[crawl] {repo_url}@{commit_sha[:12]}: {len(results['sorries'])} sorries")
        return results
