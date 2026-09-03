"""Tests for the crawler's orphan identification.

The MorphCloud SDK cannot be called from tests, so this covers the predicate
that decides which instances the sweeper is allowed to stop. A mistake here
stops someone's running agent experiment, which is why it is the part with a
test.
"""

import asyncio
import threading
from contextlib import nullcontext
from types import SimpleNamespace

from sorrydb.runners import morphcloud_crawler
from sorrydb.runners.morphcloud_crawler import (
    CRAWLER_ROLE,
    CRAWLER_ROLE_KEY,
    stale_crawler_instances,
)

NOW = 1_800_000_000.0
HOUR = 3600
MIN_AGE = 2400


def _instance(name, age_seconds, metadata):
    return SimpleNamespace(
        id=name, created=NOW - age_seconds, metadata=dict(metadata)
    )


def test_stale_crawler_instances_selects_only_our_old_ones():
    stale_crawler = _instance("stale-crawler", 11 * HOUR, {CRAWLER_ROLE_KEY: CRAWLER_ROLE})
    also_stale = _instance("also-stale", MIN_AGE, {CRAWLER_ROLE_KEY: CRAWLER_ROLE})

    instances = [
        stale_crawler,
        also_stale,
        # still in use by a run in progress, younger than the threshold
        _instance("fresh-crawler", 60, {CRAWLER_ROLE_KEY: CRAWLER_ROLE}),
        # the agent runner's experiments, old but not ours to touch
        _instance(
            "agent-run",
            11 * HOUR,
            {"name": "mathlib4_abc123_rfl_id0", "sorry_id": "id0"},
        ),
        # untagged, could be anyone's, including the leak that started all this
        _instance("untagged-old", 24 * HOUR, {}),
        # a different sorrydb role, not the crawler
        _instance("other-role", 24 * HOUR, {CRAWLER_ROLE_KEY: "agent"}),
    ]

    selected = stale_crawler_instances(instances, NOW, MIN_AGE)

    assert [i.id for i in selected] == ["stale-crawler", "also-stale"]


def test_stale_crawler_instances_selects_nothing_without_our_tag():
    instances = [
        _instance("agent-run", 48 * HOUR, {"name": "some_experiment"}),
        _instance("untagged", 48 * HOUR, {}),
    ]

    assert stale_crawler_instances(instances, NOW, MIN_AGE) == []


def test_crawler_client_tags_the_instances_abuild_starts():
    """Snapshot.abuild reaches its instance through client.instances.astart.

    That indirection is the only seam for putting a TTL and our tag on the build
    VM, so assert the override is actually on the path abuild uses. Constructing
    a client makes no network call.
    """
    from morphcloud.api import MorphCloudClient

    from sorrydb.runners.morphcloud_crawler import (
        INSTANCE_TTL_SECONDS,
        _CrawlerInstanceAPI,
        _CrawlerMorphClient,
    )

    client = _CrawlerMorphClient(api_key="test-key")

    # what abuild does: self._api._client.instances.astart(...)
    assert isinstance(client.snapshots._client.instances, _CrawlerInstanceAPI)
    assert isinstance(client, MorphCloudClient)

    metadata, ttl_seconds, ttl_action = client.instances._defaults(None, None, None)
    assert metadata == {CRAWLER_ROLE_KEY: CRAWLER_ROLE}
    assert ttl_seconds == INSTANCE_TTL_SECONDS
    assert ttl_action == "stop"

    # an explicit TTL and extra metadata are preserved, and still tagged
    metadata, ttl_seconds, _ = client.instances._defaults({"name": "n"}, 99, None)
    assert metadata == {"name": "n", CRAWLER_ROLE_KEY: CRAWLER_ROLE}
    assert ttl_seconds == 99


# --- build step guards -------------------------------------------------------
#
# A repo with no candidate sorry files must not pay for `lake exe cache get` or
# `lake build`. The shell and marker plumbing cannot be exercised against real
# Morph, so these lock the shape of it: an edit that drops a guard fails here
# rather than silently paying for every build again.


class FakeInstance:
    """Records the commands a build step runs, and replays canned results."""

    def __init__(self, *results):
        self.commands = []
        self.results = list(results)

    def exec(self, command):
        self.commands.append(command)
        return self.results.pop(0)


def _result(exit_code=0, stdout=""):
    return SimpleNamespace(exit_code=exit_code, stdout=stdout, stderr="")


def test_lake_build_step_is_guarded_by_the_marker():
    from sorrydb.runners.morphcloud_crawler import CANDIDATES_MARKER, _build_steps

    steps = _build_steps("https://github.com/org/repo", "a" * 40, "deadbeef")
    build_step = steps[-1]

    assert isinstance(build_step, str)
    assert "lake build" in build_step
    assert f"test -f {CANDIDATES_MARKER} ||" in build_step
    assert "skipping lake build" in build_step

    # the guard has to precede the build, not merely be present
    assert build_step.index("test -f") < build_step.index("lake build")

    # the marker must live outside the checkout, or it dirties the git tree that
    # get_potential_sorry_files diffs against
    assert not CANDIDATES_MARKER.startswith("/root/repo")


def test_build_steps_order_the_guards_after_the_clone():
    from sorrydb.runners.morphcloud_crawler import _build_steps

    steps = _build_steps("https://github.com/org/repo", "a" * 40, "deadbeef")

    # the candidate check digests by source and ignores its closure, so it only
    # stays per-repo while it sits after the clone step in the digest chain
    assert "git clone" in steps[3]
    assert "_create_candidate_check_step" in steps[4].__qualname__
    assert "_create_guarded_cache_step" in steps[5].__qualname__
    assert "lake build" in steps[6]


def test_build_step_prefix_is_identical_across_repos():
    """Morph reuses the cached prefix only while the leading steps do not vary."""
    from sorrydb.runners.morphcloud_crawler import _build_steps

    a = _build_steps("https://github.com/org/repo-a", "a" * 40, "deadbeef")
    b = _build_steps("https://github.com/org/repo-b", "b" * 40, "deadbeef")

    assert a[:3] == b[:3]
    assert len(a) == len(b)  # the step list must not vary per repo


def test_candidate_check_uses_the_real_predicate_not_a_grep():
    from sorrydb.runners.morphcloud_crawler import (
        CANDIDATES_MARKER,
        _create_candidate_check_step,
    )

    step = _create_candidate_check_step("https://github.com/leanprover-community/mathlib4")
    instance = FakeInstance(_result(stdout="candidate_files=0\n"))

    step(instance)

    (command,) = instance.commands
    # mathlib's candidate set is empty through the diff filter, not through the
    # absence of the string, so grepping for "sorry" would not skip it
    assert "sorrydb.cli.count_candidate_sorries" in command
    assert "grep" not in command
    assert f"--marker {CANDIDATES_MARKER}" in command
    assert "leanprover-community/mathlib4" in command


def test_candidate_check_builds_anyway_when_it_cannot_decide():
    """A mismatch must degrade to slow, not to wrong."""
    from sorrydb.runners.morphcloud_crawler import (
        CANDIDATES_MARKER,
        _create_candidate_check_step,
    )

    step = _create_candidate_check_step("https://github.com/org/repo")
    instance = FakeInstance(_result(exit_code=1, stdout="boom"), _result())

    step(instance)

    assert instance.commands[-1] == f"touch {CANDIDATES_MARKER}"


def test_guarded_cache_step_skips_the_download_without_the_marker():
    from sorrydb.runners.morphcloud_crawler import (
        CANDIDATES_MARKER,
        _create_guarded_cache_step,
    )

    step = _create_guarded_cache_step()

    # marker absent: the marker test is the only command that runs
    absent = FakeInstance(_result(exit_code=1))
    step(absent)
    assert absent.commands == [f"test -f {CANDIDATES_MARKER}"]

    # marker present: it goes on to the shared cache step
    present = FakeInstance(_result(exit_code=0), _result(exit_code=1), _result())
    step(present)
    assert present.commands[0] == f"test -f {CANDIDATES_MARKER}"
    assert len(present.commands) > 1


def test_candidate_check_does_not_pipe_away_the_exit_code():
    """A pipeline exits with its last command's status, hiding real failures."""
    from sorrydb.runners.morphcloud_crawler import _create_candidate_check_step

    step = _create_candidate_check_step("https://github.com/org/repo")
    instance = FakeInstance(_result(stdout="candidate_files=3\n"))

    step(instance)

    assert "|" not in instance.commands[0]


def test_candidate_check_builds_anyway_on_unparseable_output():
    from sorrydb.runners.morphcloud_crawler import (
        CANDIDATES_MARKER,
        _create_candidate_check_step,
    )

    step = _create_candidate_check_step("https://github.com/org/repo")
    # exit code 0 but no count, which is what a piped-away failure looks like
    instance = FakeInstance(_result(stdout="Traceback...\n"), _result())

    step(instance)

    assert instance.commands[-1] == f"touch {CANDIDATES_MARKER}"


def test_prefetch_runs_max_workers_extractions_at_once(monkeypatch):
    """max_workers must be the real concurrency, not just the semaphore's.

    The blocking morphcloud calls go through asyncio.to_thread, so they share
    the loop's default executor. That pool is min(32, cpu_count + 4) unless
    _prefetch_async resizes it, which would cap a run well below the requested
    worker count on any host. 40 workers is above the 32 ceiling, so this
    deadlocks on the barrier if the resize is ever dropped.
    """
    workers = 40
    barrier = threading.Barrier(workers, timeout=60)

    def blocking(commit_sha):
        if commit_sha == "warmup":
            return  # prefetch deliberately runs the first item alone
        barrier.wait()

    async def fake_extract(repo_url, branch, commit_sha, logger):
        await asyncio.to_thread(blocking, commit_sha)
        return {"repo": repo_url}

    monkeypatch.setattr(morphcloud_crawler, "_extract_async", fake_extract)
    monkeypatch.setattr(morphcloud_crawler, "_crawl_logger", lambda *_: nullcontext(SimpleNamespace(info=lambda *_: None)))

    work = [("https://github.com/o/warm", "main", "warmup")] + [
        (f"https://github.com/o/r{i}", "main", f"sha{i}") for i in range(workers)
    ]

    cache = asyncio.run(morphcloud_crawler._prefetch_async(work, workers))

    # gather(return_exceptions=True) turns a broken barrier into a cache value.
    assert [v for v in cache.values() if isinstance(v, BaseException)] == []
    assert len(cache) == workers + 1
