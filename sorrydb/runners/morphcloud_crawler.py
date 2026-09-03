"""Crawl-side MorphCloud runner.

Follows the two-phase pattern of morphcloud_runner: first build a snapshot in
which the target repository is already cloned and compiled, then start an
instance from that snapshot just long enough to run the extraction entrypoint
and download the resulting JSON.

`prefetch` extracts a whole work list in parallel and returns a cache that
build_database.cached_extractor replays, so `update_database` can build every
repo on a fresh VM instead of on the machine running the crawl. For a single
repo, call it with a one item work list and max_workers=1.
"""

import asyncio
import json
import os
import shlex
import signal
import sys
import tempfile
import time
from pathlib import Path

from git import Repo
from morphcloud.api import Instance, InstanceAPI, MorphCloudClient

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
# Concurrent VMs during a prefetch. The 375-repo bootstrap is hopeless serially.
PREFETCH_WORKERS = int(os.environ.get("SORRYDB_MORPH_WORKERS", "8"))

# Every VM we create is tagged with this, so the sweeper can identify ours
# positively. The agent runner's instances do not carry it and are never touched.
CRAWLER_ROLE_KEY = "sorrydb_role"
CRAWLER_ROLE = "crawler"

# TTL on every VM we create, so an orphan stops itself even when our process
# never gets to clean up. Longer than BUILD_TIMEOUT, so it never truncates a
# build that our own timeout would not already have killed.
INSTANCE_TTL_SECONDS = int(
    os.environ.get("SORRYDB_MORPH_TTL", str(BUILD_TIMEOUT + 600))
)
# TTL on an extraction instance. Longer than INSTANCE_TTL_SECONDS by default,
# because an extraction may legitimately run for EXTRACT_TIMEOUT.
EXTRACT_TTL_SECONDS = EXTRACT_TIMEOUT + 120

# A tagged instance younger than this may belong to a run still in progress, so
# the sweeper leaves it alone. Derived from the TTLs rather than written out, so
# raising either one cannot leave the sweeper stopping live VMs: at 2400 it used
# to classify an extraction still inside its own 3720 second TTL as stale.
SWEEP_MIN_AGE_SECONDS = max(INSTANCE_TTL_SECONDS, EXTRACT_TTL_SECONDS) + 300
# SorryDB commit with frozen package deps, so `poetry install` stays cached
FROZEN_DEPS_COMMIT = "7e6991be03405cfb334a91a67b63a2e1ee550fbe"

# Written on the VM when the repo has files that could contain sorries. The
# cache and build steps test for it and no-op without it, so a repo with nothing
# to extract does not pay for a full Lean build. Lives outside the checkout so it
# cannot dirty the git tree that get_potential_sorry_files diffs against.
CANDIDATES_MARKER = "/root/candidate_sorries.marker"


# Instances this process started and has not stopped, so a SIGTERM can take
# them down before we exit.
_live_instances: set[str] = set()


class _CrawlerInstanceAPI(InstanceAPI):
    """InstanceAPI that tags and time-limits every instance it starts.

    Snapshot.abuild starts its own instance through
    self._api._client.instances.astart, gives it no TTL and no metadata, and only
    stops it in a finally on the normal path. A killed coordinator therefore
    leaks a 4 vCPU / 16 GiB VM that bills until a human notices, and the leak
    carries no metadata to identify it by. Overriding the API the SDK reaches
    through is the seam that fixes both, without reimplementing the build loop
    against the SDK's private cache-prefix helpers.
    """

    def _defaults(self, metadata, ttl_seconds, ttl_action):
        metadata = dict(metadata or {})
        metadata[CRAWLER_ROLE_KEY] = CRAWLER_ROLE
        if ttl_seconds is None:
            ttl_seconds = INSTANCE_TTL_SECONDS
        return metadata, ttl_seconds, ttl_action or "stop"

    def start(
        self, snapshot_id, metadata=None, ttl_seconds=None, ttl_action=None, **kwargs
    ) -> Instance:
        metadata, ttl_seconds, ttl_action = self._defaults(
            metadata, ttl_seconds, ttl_action
        )
        instance = super().start(
            snapshot_id, metadata, ttl_seconds, ttl_action, **kwargs
        )
        _live_instances.add(instance.id)
        return instance

    async def astart(
        self, snapshot_id, metadata=None, ttl_seconds=None, ttl_action=None, **kwargs
    ) -> Instance:
        metadata, ttl_seconds, ttl_action = self._defaults(
            metadata, ttl_seconds, ttl_action
        )
        instance = await super().astart(
            snapshot_id, metadata, ttl_seconds, ttl_action, **kwargs
        )
        _live_instances.add(instance.id)
        return instance

    def stop(self, instance_id: str) -> None:
        _live_instances.discard(instance_id)
        super().stop(instance_id)

    async def astop(self, instance_id: str) -> None:
        _live_instances.discard(instance_id)
        await super().astop(instance_id)


class _CrawlerMorphClient(MorphCloudClient):
    """Client whose instances all carry the crawler tag and a TTL."""

    @property
    def instances(self) -> InstanceAPI:
        return _CrawlerInstanceAPI(self)


def _client() -> MorphCloudClient:
    return _CrawlerMorphClient(api_key=MORPH_API_KEY)


def stale_crawler_instances(
    instances, now: float, min_age_seconds: int = SWEEP_MIN_AGE_SECONDS
) -> list:
    """Select the instances that are provably ours and old enough to be orphans.

    Both conditions are required, and neither is sufficient. The tag alone would
    stop a crawler VM that a concurrent run is still using. Age alone would stop
    the agent runner's experiments, which legitimately run for hours and are not
    ours to touch.
    """
    return [
        instance
        for instance in instances
        if instance.metadata.get(CRAWLER_ROLE_KEY) == CRAWLER_ROLE
        and now - instance.created >= min_age_seconds
    ]


def list_crawler_instances() -> list:
    """Every instance tagged as ours, filtered server side."""
    return _client().instances.list(metadata={CRAWLER_ROLE_KEY: CRAWLER_ROLE})


def sweep_orphaned_instances(min_age_seconds: int = SWEEP_MIN_AGE_SECONDS) -> int:
    """Stop crawler instances left behind by an earlier run. Returns how many."""
    api = _client().instances
    try:
        instances = api.list(metadata={CRAWLER_ROLE_KEY: CRAWLER_ROLE})
    except Exception as e:
        print(f"[sweep] Could not list instances: {e}")
        return 0

    stale = stale_crawler_instances(instances, time.time(), min_age_seconds)
    if not stale:
        return 0

    print(f"[sweep] Stopping {len(stale)} orphaned crawler instances")
    stopped = 0
    for instance in stale:
        try:
            api.stop(instance.id)
            stopped += 1
            print(f"[sweep] Stopped {instance.id}")
        except Exception as e:
            print(f"[sweep] Could not stop {instance.id}: {e}")
    return stopped


def _stop_live_instances():
    api = _client().instances
    for instance_id in list(_live_instances):
        try:
            api.stop(instance_id)
            print(f"[crawl] Stopped in-flight instance {instance_id}")
        except Exception as e:
            print(f"[crawl] Could not stop {instance_id}: {e}")


def _handle_termination(signum, _frame):
    print(f"[crawl] Signal {signum}: stopping {len(_live_instances)} in-flight VMs")
    _stop_live_instances()
    sys.exit(128 + signum)


def install_signal_handlers():
    """Stop in-flight VMs on SIGTERM and SIGINT before exiting.

    Cloud Run sends SIGTERM before killing a task, so this covers the timeout
    case. SIGKILL cannot be caught, which is what the TTL and the sweeper are
    for.
    """
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handle_termination)
        except ValueError:
            # not the main thread, nothing we can install
            return


def _sorrydb_commit() -> str:
    """The SorryDB commit the VM checks out. It must already be pushed.

    The Docker image has no git checkout, so it passes SORRYDB_COMMIT instead.
    """
    return os.environ.get("SORRYDB_COMMIT") or Repo(".").head.commit.hexsha


def _checkout_dir_name(repo_url: str) -> str:
    """Directory name prepare_repository derives from a remote URL."""
    name = repo_url.rstrip("/").split("/")[-1]
    return name[:-4] if name.endswith(".git") else name


def _create_candidate_check_step(repo_url: str):
    """Create a step that counts candidate sorry files and writes the marker.

    Runs the real get_potential_sorry_files on the VM rather than grepping for
    "sorry", because mathlib's candidate set is empty on master through the
    diff filter, not through the absence of the string.

    A callable rather than a shell step so the count reaches the coordinator's
    own log, where it can be measured across the repo list.

    Note this step must stay after the clone step. The SDK digests a callable by
    its source, ignoring closure variables, so `repo_url` does not vary the
    digest. Per-repo digests come from the chain through the clone step's text.
    """

    def step(instance: Instance) -> None:
        # Deliberately not piped through tee: a pipeline exits with the status of
        # its last command, which would hide a failure of the module itself.
        result = instance.exec(
            f"cd SorryDB && "
            f'export PATH="$HOME/.local/bin:$PATH" && '
            f"poetry run python -m sorrydb.cli.count_candidate_sorries "
            f"--repo-url {shlex.quote(repo_url)} "
            f"--repo-path /root/repo "
            f"--marker {CANDIDATES_MARKER}"
        )

        count = ""
        if result.exit_code == 0:
            before, found, after = result.stdout.rpartition("candidate_files=")
            count = after.strip() if found else ""

        if not count:
            # Could not decide, so build. A marker that wrongly says "build"
            # only wastes time; one that wrongly says "skip" would make the
            # extraction instance build instead, which is slower still.
            print(
                f"[candidates] {repo_url}: check inconclusive "
                f"(exit_code={result.exit_code}), building anyway"
            )
            print(f"[candidates] {repo_url}: stdout was {result.stdout.strip()!r}")
            instance.exec(f"touch {CANDIDATES_MARKER}")
            return

        if count == "0":
            print(
                f"[candidates] {repo_url}: 0 candidate sorry files, "
                f"skipping cache get and lake build"
            )
        else:
            print(f"[candidates] {repo_url}: {count} candidate sorry files")

    return step


def _create_guarded_cache_step():
    """lake exe cache get, but only when the repo has candidate sorry files.

    Wraps the runner's retry step rather than changing it, since the agent
    runner shares that step and knows nothing about the marker.
    """
    download_cache = _create_cache_retry_step()

    def step(instance: Instance) -> None:
        if instance.exec(f"test -f {CANDIDATES_MARKER}").exit_code != 0:
            print("[cache] No candidate sorry files, skipping cache download")
            return
        download_cache(instance)

    return step


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
            # A pipeline exits with its last command's status, and sh exits 0 on
            # empty input, so a failed curl would otherwise be snapshotted as a
            # success without elan. This step is in the shared prefix, so that
            # poisoned layer would be inherited by every later repo.
            'test -x "$HOME/.elan/bin/elan" && '
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
        # Step 4b: count candidate sorry files and write the marker (callable)
        _create_candidate_check_step(repo_url),
        # Step 4c: get lake cache with retry, skipped without the marker (callable)
        _create_guarded_cache_step(),
        # Step 4d: build the target repo, skipped without the marker. Static
        # text, so Morph's step caching is unaffected by the decision.
        (
            "("
            f"test -f {CANDIDATES_MARKER} || "
            "{ echo 'no candidate sorry files, skipping lake build'; exit 0; }; "
            "cd /root/repo && "
            'export PATH="$HOME/.elan/bin:$PATH" && '
            "lake build"
            ") > /tmp/step_4d.log 2>&1"
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

    steps = _build_steps(repo_url, commit_sha, _sorrydb_commit())

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
    mc = _client()
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
        ttl_seconds=EXTRACT_TTL_SECONDS,
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


def _crawl_logger(repo_url: str, commit_sha: str):
    """Per (repo, commit) log file, so concurrent extractions do not interleave."""
    label = f"{sanitize_repo_name(repo_url)}_{commit_sha[:12]}"
    return setup_logger(
        f"morphcloud_crawl_{label}", _get_log_path("morphcloud_crawl", f"{label}.log")
    )


async def _prefetch_async(work: list[tuple[str, str, str]], max_workers: int) -> dict:
    semaphore = asyncio.Semaphore(max_workers)

    async def extract_one(repo_url: str, branch: str, commit_sha: str) -> dict:
        async with semaphore:
            with _crawl_logger(repo_url, commit_sha) as logger:
                logger.info(f"Extracting {repo_url}@{commit_sha} on branch {branch}")
                return await _extract_async(repo_url, branch, commit_sha, logger)

    # The SorryDB commit is embedded in the shared build prefix, and every
    # deploy changes it, so the first crawl afterwards starts cold. Fanning out
    # immediately would have all max_workers repeat the same apt, elan and
    # poetry install before any of them populated the cache, so warm it with one
    # repo first and let the rest hit the cached layers.
    warmup = await asyncio.gather(extract_one(*work[0]), return_exceptions=True)
    rest = await asyncio.gather(
        *[extract_one(*item) for item in work[1:]], return_exceptions=True
    )
    results = list(warmup) + list(rest)

    return {
        (repo_url, commit_sha): result
        for (repo_url, _, commit_sha), result in zip(work, results)
    }


def prefetch(
    work: list[tuple[str, str, str]], max_workers: int = PREFETCH_WORKERS
) -> dict:
    """Extract every (repo_url, branch, commit_sha) of `work` in parallel.

    Returns {(repo_url, commit_sha): extraction dict, or the exception that
    failed it}, which build_database.cached_extractor replays.
    """
    if not work:
        return {}

    install_signal_handlers()
    print(f"[crawl] Prefetching {len(work)} commits with {max_workers} workers")
    cache = asyncio.run(_prefetch_async(work, max_workers))
    failed = sum(1 for result in cache.values() if isinstance(result, BaseException))
    print(f"[crawl] Prefetched {len(cache) - failed} commits, {failed} failed")
    return cache


if __name__ == "__main__":
    # Manual orphan cleanup:
    #   python -m sorrydb.runners.morphcloud_crawler          lists crawler VMs
    #   python -m sorrydb.runners.morphcloud_crawler --stop   stops the stale ones
    import argparse

    parser = argparse.ArgumentParser(description="List or stop crawler MorphCloud VMs")
    parser.add_argument(
        "--stop", action="store_true", help="stop the stale instances, not just list"
    )
    parser.add_argument(
        "--min-age",
        type=int,
        default=SWEEP_MIN_AGE_SECONDS,
        help=f"seconds an instance must have run to count as stale (default {SWEEP_MIN_AGE_SECONDS})",
    )
    args = parser.parse_args()

    now = time.time()
    instances = list_crawler_instances()
    stale = {i.id for i in stale_crawler_instances(instances, now, args.min_age)}

    for instance in instances:
        age = int(now - instance.created)
        mark = "STALE" if instance.id in stale else "in use"
        name = instance.metadata.get("name", "")
        print(f"{instance.id}  {age // 60}m  {mark}  {name}")

    print(f"{len(instances)} crawler instances, {len(stale)} stale")
    if args.stop:
        print(f"Stopped {sweep_orphaned_instances(args.min_age)}")
