import hashlib
import json
import shutil
from pathlib import Path

import pytest
from git import Actor, Repo

from sorrydb.database.build_database import (
    prepare_and_process_lean_repo,
    update_database,
)
from sorrydb.utils.git_ops import remote_heads_hash

# A dependency-free Lean project, which CI's lean-action step already installs a
# toolchain for (see lake-package-directory in .github/workflows/ci.yml).
MOCK_LEAN_REPOSITORY = Path(__file__).parent / "mock_lean_repository"
FIXTURE_BRANCH = "main"
FIXTURE_EMAIL = "test@sorrydb.invalid"
FIXTURE_ACTOR = Actor("SorryDB Test", FIXTURE_EMAIL)
# Fixed identity and dates make the commit sha reproducible, so assertions on it
# stay meaningful without being regenerated.
FIXTURE_COMMIT_DATE = "2026-01-15 12:00:00 +0000"
FIXTURE_BLAME_DATE = "2026-01-15T12:00:00+00:00"
FIXTURE_VISITED_BEFORE = "2026-01-01T00:00:00+00:00"


def make_local_lean_repo(path: Path) -> str:
    """Copy the Lean fixture into a real git repo, and return its head sha.

    update_database discovers what to crawl by asking the remote for its branch
    heads, so a test pointed at GitHub reports whatever was pushed there most
    recently. Serving the fixture from a local repo is the only way to make the
    loop deterministic, and it also keeps mathlib out of CI.
    """
    shutil.copytree(
        MOCK_LEAN_REPOSITORY, path, ignore=shutil.ignore_patterns(".lake")
    )
    repo = Repo.init(path, initial_branch=FIXTURE_BRANCH)
    repo.git.add(A=True)
    repo.index.commit(
        "mock lean repository",
        author=FIXTURE_ACTOR,
        committer=FIXTURE_ACTOR,
        author_date=FIXTURE_COMMIT_DATE,
        commit_date=FIXTURE_COMMIT_DATE,
    )
    return repo.head.commit.hexsha


def _location_key(location, goal):
    return (
        location["path"],
        location["start_line"],
        location["start_column"],
        location["end_line"],
        location["end_column"],
        goal,
    )


def expected_fixture_sorries() -> set:
    """The sorries the REPL finds in the fixture, as recorded in the fixture.

    Reading them from mock_lean_repository/sorries.json keeps one source of
    truth: test_sorry_extraction.py cross-references the same file, so editing a
    .lean file means updating one place rather than a golden database too.
    """
    with open(MOCK_LEAN_REPOSITORY / "sorries.json", encoding="utf-8") as f:
        recorded = json.load(f)
    return {_location_key(s["location"], s["goal"]) for s in recorded}


def extracted_sorries(database: dict) -> set:
    return {
        _location_key(s["location"], s["debug_info"]["goal"])
        for s in database["sorries"]
    }


def fixture_lean_version() -> str:
    toolchain = (MOCK_LEAN_REPOSITORY / "lean-toolchain").read_text()
    return toolchain.strip().split(":", 1)[1]


# Deselected in CI. sorryClientTestRepoMath pulls mathlib and eight more
# packages, so this does a multi-GB `lake exe cache get` and dominates the
# suite's runtime. It is also the last test pointed at live GitHub repos, so run
# it deliberately rather than on every merge.
@pytest.mark.local_only
def test_prepare_and_process_lean_repo_with_mutiple_lean_versions(tmp_path):
    """
    Verify that the database builder can handle repositories
    that use different versions of Lean.

    These two repos track different Lean releases, currently v4.31.0 for
    sorryClientTestRepo and v4.24.0 for sorryClientTestRepoMath. The versions
    move as the repos are upgraded, which is fine here because this test only
    asserts that sorries were found, not which ones.
    """
    # first do non-Math version for quicker fail
    repoResults = prepare_and_process_lean_repo(
        repo_url="https://github.com/austinletson/sorryClientTestRepo",
        lean_data=tmp_path / "repo",
    )
    assert len(repoResults["sorries"]) > 0
    # now do MathLib dependent test
    mathRepoResults = prepare_and_process_lean_repo(
        repo_url="https://github.com/austinletson/sorryClientTestRepoMath",
        lean_data=tmp_path / "repo_math",
    )
    assert len(mathRepoResults["sorries"]) > 0


def assert_crawled_fixture(database: dict, repo_path, head_sha, update_stats):
    """Assert a real crawl of the local Lean fixture accounts for every sorry.

    The fixture has no dependencies, and `run_tac`, which the parent type query
    is built on, is parser only in core Lean: its elaborator lives in Mathlib.
    So the query cannot be answered here, and the strict Prop filter excludes
    every sorry. That makes these tests currently prove the pipeline runs and
    accounts for what it dropped, rather than proving goal extraction.

    The accounting invariant below holds either way, so fixing the parent type
    query does not invalidate it.
    """
    remote = str(repo_path)
    expected = expected_fixture_sorries()

    sorries = [s for s in database["sorries"] if s["repo"]["remote"] == remote]
    recorded = {_location_key(s["location"], s["debug_info"]["goal"]) for s in sorries}

    repo_stats = update_stats[remote]
    commit_stats = repo_stats["counts"][head_sha]
    excluded = commit_stats["undetermined_type_excluded"]

    # Nothing invented and nothing lost without being counted
    assert recorded <= expected
    assert len(recorded) + excluded == len(expected)
    assert commit_stats["count"] == len(recorded)

    # Canary. When the parent type query is fixed this fails, which is the
    # moment to restore the goal level assertions below to real coverage.
    assert excluded == len(expected), (
        "the REPL answered the parent type query for a Mathlib free project, so "
        "extraction now works here: assert the extracted goals again"
    )
    assert recorded == set()

    # Meaningful again as soon as anything is extracted
    for sorry in sorries:
        assert sorry["repo"]["branch"] == FIXTURE_BRANCH
        assert sorry["repo"]["commit"] == head_sha
        assert sorry["repo"]["lean_version"] == fixture_lean_version()
        assert sorry["debug_info"]["url"] == (
            f"{remote}/blob/{head_sha}/{sorry['location']['path']}"
            f"#L{sorry['location']['start_line']}"
        )
        assert sorry["metadata"]["blame_date"] == FIXTURE_BLAME_DATE
        assert sorry["metadata"]["blame_email_hash"] == (
            hashlib.sha256(FIXTURE_EMAIL.encode()).hexdigest()[:12]
        )

    # The crawl itself succeeded: the repo was visited, built and accounted for,
    # and is not retried, because the query fails deterministically
    assert repo_stats["new_leaf_commit"] is True
    assert repo_stats["lake_timeout"] is None
    assert repo_stats["lean_version"] == fixture_lean_version()
    assert set(repo_stats["counts"]) == {head_sha}

    repo_entry = next(r for r in database["repos"] if r["remote_url"] == remote)
    assert repo_entry["remote_heads_hash"] == remote_heads_hash(
        remote, all_branches=False
    )
    assert repo_entry["last_time_visited"] != FIXTURE_VISITED_BEFORE


@pytest.mark.parametrize(
    "use_lean_data_dir",
    [False, True],
    ids=["without_lean_data_dir", "with_lean_data_dir"],
)
def test_update_database_single_repo(tmp_path, use_lean_data_dir):
    """Crawl one repository for real: Lean build, REPL extraction and all.

    Served from a local git repo rather than GitHub, so the loop's discovery of
    branch heads is deterministic and cannot rot when someone pushes upstream.
    """
    repo_path = tmp_path / "mock_repo"
    head_sha = make_local_lean_repo(repo_path)

    init_db = tmp_path / "init_db.json"
    _write_init_db(init_db, (str(repo_path),), last_time_visited=FIXTURE_VISITED_BEFORE)
    write_db = tmp_path / "updated_sorry_database.json"

    lean_data_arg = tmp_path / "lean_data" if use_lean_data_dir else None

    update_stats = update_database(init_db, write_db, lean_data_path=lean_data_arg)

    assert write_db.exists(), "The updated database file was not created"
    database = json.loads(write_db.read_text())

    assert set(update_stats) == {str(repo_path)}
    assert_crawled_fixture(database, repo_path, head_sha, update_stats)

    # count_new_goal counts each distinct goal once among what was recorded
    recorded_goals = {s["debug_info"]["goal"] for s in database["sorries"]}
    assert update_stats[str(repo_path)]["counts"][head_sha]["count_new_goal"] == len(
        recorded_goals
    )


def test_update_database_multiple_repo(tmp_path):
    """Crawl two repositories in one update.

    Both serve the same fixture, so they share a commit sha and a set of goals,
    which pins two things worth pinning: per-repo stats stay separate even at the
    same sha, and count_new_goal is database-wide rather than per repo.
    """
    repo_a = tmp_path / "repo_a"
    repo_b = tmp_path / "repo_b"
    sha_a = make_local_lean_repo(repo_a)
    sha_b = make_local_lean_repo(repo_b)
    assert sha_a == sha_b, "same fixture content should give the same commit sha"

    init_db = tmp_path / "init_db.json"
    _write_init_db(
        init_db,
        (str(repo_a), str(repo_b)),
        last_time_visited=FIXTURE_VISITED_BEFORE,
    )
    write_db = tmp_path / "updated_sorry_database.json"

    # A shared lean_data directory lets the REPL build be reused across repos
    update_stats = update_database(
        init_db, write_db, lean_data_path=tmp_path / "lean_data"
    )

    assert write_db.exists(), "The updated database file was not created"
    database = json.loads(write_db.read_text())

    assert set(update_stats) == {str(repo_a), str(repo_b)}
    assert_crawled_fixture(database, repo_a, sha_a, update_stats)
    assert_crawled_fixture(database, repo_b, sha_b, update_stats)

    # Every sorry in both repos is accounted for, recorded or excluded
    expected = expected_fixture_sorries()
    total_excluded = sum(
        update_stats[str(repo)]["counts"][sha]["undetermined_type_excluded"]
        for repo, sha in ((repo_a, sha_a), (repo_b, sha_b))
    )
    assert len(database["sorries"]) + total_excluded == 2 * len(expected)

    # Sorry ids include the remote, so the same sorry in two repos is two rows
    assert len({s["id"] for s in database["sorries"]}) == len(database["sorries"])

    # Goals are deduplicated across the whole database, so whatever the first
    # repo records, the second cannot record again as new
    assert update_stats[str(repo_b)]["counts"][sha_b]["count_new_goal"] == 0


def _fake_sorry(line: int) -> dict:
    return {
        "goal": f"|- goal {line}",
        "location": {
            "path": "Test/Basic.lean",
            "start_line": line,
            "start_column": 2,
            "end_line": line,
            "end_column": 7,
        },
        "blame": {
            "author_email_hash": "abc123",
            "date": "2026-08-26T00:00:00+00:00",
        },
    }


def _write_init_db(path, repo_urls, last_time_visited="2026-08-25T00:00:00+00:00"):
    path.write_text(
        json.dumps(
            {
                "repos": [
                    {
                        "remote_url": url,
                        "last_time_visited": last_time_visited,
                        "remote_heads_hash": None,
                    }
                    for url in repo_urls
                ],
                "sorries": [],
            }
        )
    )


REPO_A = "https://example.com/org/repo-a"
REPO_B = "https://example.com/org/repo-b"
COMMIT_A = "a" * 40
COMMIT_B = "b" * 40


def test_update_database_with_fake_extractor(tmp_path, monkeypatch):
    """Drive the crawl loop with a fake extractor, so no Lean toolchain is needed.

    Also checks that the database is checkpointed after every repo: by the time
    the second repo is extracted, the first repo's watermarks are already on disk.
    """
    import sorrydb.database.build_database as bd

    repo_a, repo_b = REPO_A, REPO_B

    init_db = tmp_path / "init_db.json"
    _write_init_db(init_db, (repo_a, repo_b))
    write_db = tmp_path / "updated_db.json"

    commits = {
        repo_a: [
            {"sha": COMMIT_A, "branch": "main", "date": "2026-08-26T00:00:00+00:00"}
        ],
        repo_b: [
            {"sha": COMMIT_B, "branch": "main", "date": "2026-08-27T00:00:00+00:00"}
        ],
    }

    monkeypatch.setattr(
        bd, "remote_heads_hash", lambda url, all_branches=False: f"heads-{url[-1]}"
    )
    monkeypatch.setattr(
        bd, "leaf_commits", lambda url, all_branches=False: commits[url]
    )

    extractor_calls = []
    checkpoints = {}

    def fake_extract(repo_url, branch, commit_sha, lean_data):
        extractor_calls.append((repo_url, branch, commit_sha))
        checkpoints[repo_url] = (
            json.loads(write_db.read_text()) if write_db.exists() else None
        )
        return {
            "metadata": {"lean_version": "v4.17.0"},
            "sorries": [_fake_sorry(4)],
        }

    update_stats = update_database(init_db, write_db, extract=fake_extract)

    # The extractor is called once per new leaf commit, with that commit's sha
    assert extractor_calls == [
        (repo_a, "main", COMMIT_A),
        (repo_b, "main", COMMIT_B),
    ]

    # Nothing on disk yet when the first repo is extracted
    assert checkpoints[repo_a] is None

    # By the time the second repo is extracted, repo-a is checkpointed
    checkpoint = checkpoints[repo_b]
    assert checkpoint is not None
    checkpointed_a = next(r for r in checkpoint["repos"] if r["remote_url"] == repo_a)
    assert checkpointed_a["remote_heads_hash"] == "heads-a"
    assert checkpointed_a["last_time_visited"] != "2026-08-25T00:00:00+00:00"
    assert len(checkpoint["sorries"]) == 1

    # The final database holds the sorries from both repos
    final_db = json.loads(write_db.read_text())
    assert len(final_db["sorries"]) == 2
    assert {s["repo"]["remote"] for s in final_db["sorries"]} == {repo_a, repo_b}
    assert {s["repo"]["commit"] for s in final_db["sorries"]} == {COMMIT_A, COMMIT_B}
    assert all(s["repo"]["lean_version"] == "v4.17.0" for s in final_db["sorries"])

    assert update_stats[repo_a]["counts"][COMMIT_A]["count"] == 1
    assert update_stats[repo_b]["counts"][COMMIT_B]["count"] == 1


def test_update_database_replays_a_prefetched_cache(tmp_path):
    """The parallel path: a prefetched listing and extraction cache, no network."""
    from sorrydb.database.build_database import cached_extractor, cached_lister

    init_db = tmp_path / "init_db.json"
    _write_init_db(init_db, (REPO_A, REPO_B))
    write_db = tmp_path / "updated_db.json"

    listed_at = "2026-09-01T00:00:00+00:00"
    listings = {
        REPO_A: (
            "heads-a",
            [{"sha": COMMIT_A, "branch": "main", "date": "2026-08-26T00:00:00+00:00"}],
            listed_at,
        ),
        REPO_B: (
            "heads-b",
            [{"sha": COMMIT_B, "branch": "main", "date": "2026-08-27T00:00:00+00:00"}],
            listed_at,
        ),
    }
    extraction = {"metadata": {"lean_version": "v4.17.0"}, "sorries": [_fake_sorry(4)]}
    cache = {
        (REPO_A, COMMIT_A): extraction,
        # repo-b's VM failed, so the cache holds the exception instead
        (REPO_B, COMMIT_B): RuntimeError("build failed on repo-b"),
    }

    update_stats = update_database(
        init_db,
        write_db,
        extract=cached_extractor(cache),
        list_commits=cached_lister(listings),
    )

    final_db = json.loads(write_db.read_text())

    # repo-a's sorries survive repo-b's failure
    assert len(final_db["sorries"]) == 1
    assert final_db["sorries"][0]["repo"]["remote"] == REPO_A
    assert final_db["sorries"][0]["repo"]["commit"] == COMMIT_A
    assert update_stats[REPO_A]["counts"][COMMIT_A]["count"] == 1
    assert COMMIT_B not in update_stats[REPO_B]["counts"]

    # The replayed listing time, not a pass-two timestamp, becomes the watermark
    repos = {r["remote_url"]: r for r in final_db["repos"]}
    assert repos[REPO_A]["last_time_visited"] == listed_at
    assert repos[REPO_A]["remote_heads_hash"] == "heads-a"


def test_update_database_skips_repos_missing_from_the_cache(tmp_path):
    """A repo the prefetch never listed keeps its watermarks for the next run."""
    from sorrydb.database.build_database import cached_extractor, cached_lister

    init_db = tmp_path / "init_db.json"
    _write_init_db(init_db, (REPO_A, REPO_B))
    write_db = tmp_path / "updated_db.json"

    listings = {
        REPO_A: (
            "heads-a",
            [{"sha": COMMIT_A, "branch": "main", "date": "2026-08-26T00:00:00+00:00"}],
            "2026-09-01T00:00:00+00:00",
        )
    }
    cache = {
        (REPO_A, COMMIT_A): {
            "metadata": {"lean_version": "v4.17.0"},
            "sorries": [_fake_sorry(4)],
        }
    }

    update_database(
        init_db,
        write_db,
        extract=cached_extractor(cache),
        list_commits=cached_lister(listings),
    )

    final_db = json.loads(write_db.read_text())
    assert len(final_db["sorries"]) == 1

    repos = {r["remote_url"]: r for r in final_db["repos"]}
    assert repos[REPO_B]["last_time_visited"] == "2026-08-25T00:00:00+00:00"
    assert repos[REPO_B]["remote_heads_hash"] is None


def test_listings_to_work_extracts_a_shared_head_once():
    from sorrydb.database.build_database import listings_to_work

    listings = {
        REPO_A: (
            "heads-a",
            [
                {"sha": COMMIT_A, "branch": "main"},
                {"sha": COMMIT_A, "branch": "release"},  # same head, one VM
                {"sha": COMMIT_B, "branch": "other"},
            ],
            "2026-09-01T00:00:00+00:00",
        ),
        REPO_B: (None, [], "2026-09-01T00:00:00+00:00"),  # nothing new
    }

    assert listings_to_work(listings) == [
        (REPO_A, "main", COMMIT_A),
        (REPO_A, "other", COMMIT_B),
    ]


def test_update_database_retries_a_repo_whose_extractions_all_failed(
    tmp_path, monkeypatch
):
    """A repo where nothing extracted keeps its watermarks, so it is retried.

    A repo where only some commits failed still advances, because re-extracting
    the commits that succeeded costs a VM each and add_sorry does not dedupe.
    """
    import sorrydb.database.build_database as bd

    init_db = tmp_path / "init_db.json"
    _write_init_db(init_db, (REPO_A, REPO_B))
    write_db = tmp_path / "updated_db.json"

    commits = {
        # repo-a: the first commit extracts, the second fails, so partial
        REPO_A: [
            {"sha": COMMIT_A, "branch": "main", "date": "2026-08-26T00:00:00+00:00"},
            {"sha": "c" * 40, "branch": "other", "date": "2026-08-27T00:00:00+00:00"},
        ],
        # repo-b: its only commit fails, so total
        REPO_B: [
            {"sha": COMMIT_B, "branch": "main", "date": "2026-08-27T00:00:00+00:00"}
        ],
    }

    monkeypatch.setattr(
        bd, "remote_heads_hash", lambda url, all_branches=False: f"heads-{url[-1]}"
    )
    monkeypatch.setattr(
        bd, "leaf_commits", lambda url, all_branches=False: commits[url]
    )

    def fake_extract(repo_url, branch, commit_sha, lean_data):
        if commit_sha != COMMIT_A:
            raise RuntimeError(f"build failed on {commit_sha[:12]}")
        return {"metadata": {"lean_version": "v4.17.0"}, "sorries": [_fake_sorry(4)]}

    update_database(init_db, write_db, extract=fake_extract)

    final_db = json.loads(write_db.read_text())
    repos = {r["remote_url"]: r for r in final_db["repos"]}

    # repo-a partially succeeded, so it advances as it does today
    assert repos[REPO_A]["remote_heads_hash"] == "heads-a"
    assert repos[REPO_A]["last_time_visited"] != "2026-08-25T00:00:00+00:00"

    # repo-b extracted nothing, so it is left untouched for the next run
    assert repos[REPO_B]["remote_heads_hash"] is None
    assert repos[REPO_B]["last_time_visited"] == "2026-08-25T00:00:00+00:00"

    assert len(final_db["sorries"]) == 1
    assert final_db["sorries"][0]["repo"]["commit"] == COMMIT_A


def test_update_database_retries_a_repo_after_a_lake_timeout(tmp_path, monkeypatch):
    """The lake timeout path breaks on the first commit, which counts as total."""
    import sorrydb.database.build_database as bd

    init_db = tmp_path / "init_db.json"
    _write_init_db(init_db, (REPO_A,))
    write_db = tmp_path / "updated_db.json"

    monkeypatch.setattr(bd, "remote_heads_hash", lambda url, all_branches=False: "heads-a")
    monkeypatch.setattr(
        bd,
        "leaf_commits",
        lambda url, all_branches=False: [
            {"sha": COMMIT_A, "branch": "main", "date": "2026-08-26T00:00:00+00:00"}
        ],
    )

    def timing_out_extract(repo_url, branch, commit_sha, lean_data):
        raise bd.LakeTimeoutError("lake build timed out")

    update_stats = update_database(init_db, write_db, extract=timing_out_extract)

    assert update_stats[REPO_A]["lake_timeout"] is True

    repo = json.loads(write_db.read_text())["repos"][0]
    assert repo["remote_heads_hash"] is None
    assert repo["last_time_visited"] == "2026-08-25T00:00:00+00:00"


def test_local_lister_reads_only_the_default_branch_by_default(monkeypatch):
    """Work scales with branch heads, so the default is one branch per repo."""
    import sorrydb.database.build_database as bd

    asked = {}

    def fake_leaf_commits(url, all_branches=True):
        asked["leaf_commits"] = all_branches
        branches = [{"sha": COMMIT_A, "branch": "main", "date": "2026-08-26T00:00:00+00:00"}]
        if all_branches:
            branches.append(
                {"sha": COMMIT_B, "branch": "feature", "date": "2026-08-27T00:00:00+00:00"}
            )
        return branches

    def fake_remote_heads_hash(url, all_branches=True):
        asked["remote_heads_hash"] = all_branches
        return "heads-all" if all_branches else "heads-default"

    monkeypatch.setattr(bd, "leaf_commits", fake_leaf_commits)
    monkeypatch.setattr(bd, "remote_heads_hash", fake_remote_heads_hash)

    repo = {
        "remote_url": REPO_A,
        "last_time_visited": "2026-08-25T00:00:00+00:00",
        "remote_heads_hash": None,
    }

    new_hash, commits, _ = bd.local_lister(repo)

    # Both the listing and the change hash must be scoped to one branch, or a
    # push to a branch we ignore would trigger a pass that finds nothing to do.
    assert asked == {"leaf_commits": False, "remote_heads_hash": False}
    assert new_hash == "heads-default"
    assert [c["branch"] for c in commits] == ["main"]


def test_local_lister_reads_every_branch_when_asked(monkeypatch):
    """The feature-branch capability is retained behind the flag."""
    from functools import partial

    import sorrydb.database.build_database as bd

    asked = {}

    def fake_leaf_commits(url, all_branches=True):
        asked["leaf_commits"] = all_branches
        branches = [{"sha": COMMIT_A, "branch": "main", "date": "2026-08-26T00:00:00+00:00"}]
        if all_branches:
            branches.append(
                {"sha": COMMIT_B, "branch": "feature", "date": "2026-08-27T00:00:00+00:00"}
            )
        return branches

    def fake_remote_heads_hash(url, all_branches=True):
        asked["remote_heads_hash"] = all_branches
        return "heads-all" if all_branches else "heads-default"

    monkeypatch.setattr(bd, "leaf_commits", fake_leaf_commits)
    monkeypatch.setattr(bd, "remote_heads_hash", fake_remote_heads_hash)

    repo = {
        "remote_url": REPO_A,
        "last_time_visited": "2026-08-25T00:00:00+00:00",
        "remote_heads_hash": None,
    }

    # how the coordinator opts back in
    new_hash, commits, _ = partial(bd.local_lister, all_branches=True)(repo)

    assert asked == {"leaf_commits": True, "remote_heads_hash": True}
    assert new_hash == "heads-all"
    assert [c["branch"] for c in commits] == ["main", "feature"]


# --- unsupported toolchain pre-filter ---------------------------------------

REPL_TAGS_FIXTURE = ["v4.33.0", "v4.32.0", "v4.25.1"]


def test_unsupported_toolchain_repos_classifies_without_network():
    from sorrydb.database.build_database import unsupported_toolchain_repos

    toolchains = {
        "supported-exact": "leanprover/lean4:v4.33.0\n",
        "supported-fallback": "leanprover/lean4:v4.33.1\n",  # rescued by v4.33.0
        "unsupported-minor": "leanprover/lean4:v4.20.0\n",  # no tag in v4.20
        "unsupported-nightly": "leanprover/lean4:nightly-2022-12-23\n",
        "no-toolchain": None,
        "unreadable": "garbage\n",
    }

    reasons = unsupported_toolchain_repos(
        list(toolchains), resolve=toolchains.get, tags=REPL_TAGS_FIXTURE
    )

    assert set(reasons) == {"unsupported-minor", "unsupported-nightly", "no-toolchain", "unreadable"}
    assert reasons["unsupported-minor"] == "no REPL tag for Lean v4.20.0"
    assert reasons["no-toolchain"] == "no lean-toolchain at the default branch head"
    assert "unreadable" in reasons["unreadable"] or "garbage" in reasons["unreadable"]


def test_unsupported_toolchain_repos_fails_open_when_it_cannot_resolve():
    """A repo we could not check must be attempted, not silently skipped."""
    from sorrydb.database.build_database import unsupported_toolchain_repos

    def resolve(repo_url):
        raise RuntimeError("network is down")

    assert unsupported_toolchain_repos(
        ["anything"], resolve=resolve, tags=REPL_TAGS_FIXTURE
    ) == {}


def test_update_database_skips_unsupported_repos_without_touching_watermarks(
    tmp_path, monkeypatch
):
    """An unsupported repo yields no work items and stays cheap to re-check."""
    import sorrydb.database.build_database as bd

    init_db = tmp_path / "init_db.json"
    _write_init_db(init_db, (REPO_A, REPO_B))
    write_db = tmp_path / "updated_db.json"
    report = tmp_path / "report.md"

    listed = []

    def fake_leaf_commits(url, all_branches=False):
        listed.append(url)
        return [{"sha": COMMIT_A, "branch": "main", "date": "2026-08-26T00:00:00+00:00"}]

    monkeypatch.setattr(
        bd, "remote_heads_hash", lambda url, all_branches=False: f"heads-{url[-1]}"
    )
    monkeypatch.setattr(bd, "leaf_commits", fake_leaf_commits)

    extracted = []

    def fake_extract(repo_url, branch, commit_sha, lean_data):
        extracted.append(repo_url)
        return {"metadata": {"lean_version": "v4.17.0"}, "sorries": [_fake_sorry(4)]}

    stats = update_database(
        init_db,
        write_db,
        report_file=report,
        extract=fake_extract,
        unsupported_toolchains={REPO_B: "no REPL tag for Lean v4.33.1"},
    )

    # the unsupported repo is never listed and never extracted
    assert listed == [REPO_A]
    assert extracted == [REPO_A]

    repos = {r["remote_url"]: r for r in json.loads(write_db.read_text())["repos"]}
    assert repos[REPO_B]["last_time_visited"] == "2026-08-25T00:00:00+00:00"
    assert repos[REPO_B]["remote_heads_hash"] is None

    # it is recorded as skipped, not as a failure
    assert stats[REPO_B]["unsupported_toolchain"] == "no REPL tag for Lean v4.33.1"
    assert stats[REPO_B]["lake_timeout"] is None
    assert stats[REPO_B]["new_leaf_commit"] is None

    # a repo that was attempted normally keeps the original stats shape
    assert "unsupported_toolchain" not in stats[REPO_A]

    # and the count and reason reach the report
    report_text = report.read_text()
    assert "**Repositories skipped for unsupported toolchain:** 1" in report_text
    assert "no REPL tag for Lean v4.33.1" in report_text
    assert REPO_B in report_text


def test_processed_commit_log_reports_the_real_sorry_count(tmp_path, monkeypatch, caplog):
    """The count lives under ["counts"][sha]; reading one level up always gave 0."""
    import logging

    import sorrydb.database.build_database as bd

    init_db = tmp_path / "init_db.json"
    _write_init_db(init_db, (REPO_A,))

    monkeypatch.setattr(bd, "remote_heads_hash", lambda url, all_branches=False: "h")
    monkeypatch.setattr(
        bd,
        "leaf_commits",
        lambda url, all_branches=False: [
            {"sha": COMMIT_A, "branch": "main", "date": "2026-08-26T00:00:00+00:00"}
        ],
    )

    def fake_extract(repo_url, branch, commit_sha, lean_data):
        return {
            "metadata": {"lean_version": "v4.17.0"},
            "sorries": [_fake_sorry(4), _fake_sorry(9), _fake_sorry(14)],
        }

    with caplog.at_level(logging.INFO, logger="sorrydb.database.build_database"):
        stats = update_database(init_db, tmp_path / "out.json", extract=fake_extract)

    assert f"Processed commit {COMMIT_A} with 3 sorries" in caplog.text
    assert stats[REPO_A]["counts"][COMMIT_A]["count"] == 3


def test_logging_a_count_does_not_invent_a_stats_entry(tmp_path, monkeypatch):
    """counts is a defaultdict, so a bare lookup would materialise zero entries."""
    import sorrydb.database.build_database as bd

    init_db = tmp_path / "init_db.json"
    _write_init_db(init_db, (REPO_A,))

    monkeypatch.setattr(bd, "remote_heads_hash", lambda url, all_branches=False: "h")
    monkeypatch.setattr(
        bd,
        "leaf_commits",
        lambda url, all_branches=False: [
            {"sha": COMMIT_A, "branch": "main", "date": "2026-08-26T00:00:00+00:00"}
        ],
    )

    def extract_nothing(repo_url, branch, commit_sha, lean_data):
        return {"metadata": {"lean_version": "v4.17.0"}, "sorries": []}

    stats = update_database(init_db, tmp_path / "out.json", extract=extract_nothing)

    assert dict(stats[REPO_A]["counts"]) == {}


def test_undetermined_type_sorries_are_excluded_and_counted(tmp_path, monkeypatch):
    """Strict filter, loud accounting.

    A sorry whose goal type the REPL cannot confirm is excluded from the
    database. The original code did that silently, so a repo that lost every
    sorry looked sorry free. The count has to reach the stats and the report.
    """
    import sorrydb.database.build_database as bd

    init_db = tmp_path / "init_db.json"
    _write_init_db(init_db, (REPO_A,))
    report = tmp_path / "report.md"

    monkeypatch.setattr(bd, "remote_heads_hash", lambda url, all_branches=False: "h")
    monkeypatch.setattr(
        bd,
        "leaf_commits",
        lambda url, all_branches=False: [
            {"sha": COMMIT_A, "branch": "main", "date": "2026-08-26T00:00:00+00:00"}
        ],
    )

    def fake_extract(repo_url, branch, commit_sha, lean_data):
        # the extractor already dropped the excluded ones, and reports how many
        return {
            "metadata": {"lean_version": "v4.24.0", "undetermined_type_excluded": 2},
            "sorries": [_fake_sorry(4)],
        }

    stats = update_database(
        init_db, tmp_path / "out.json", report_file=report, extract=fake_extract
    )

    counts = stats[REPO_A]["counts"][COMMIT_A]
    assert counts["count"] == 1
    assert counts["undetermined_type_excluded"] == 2

    # the Lean version sits next to it, since that is the axis to correlate on
    assert stats[REPO_A]["lean_version"] == "v4.24.0"

    report_text = report.read_text()
    assert "**Sorries excluded, type undetermined:** 2" in report_text
    assert "v4.24.0" in report_text


def test_a_repo_whose_sorries_were_all_excluded_is_visible(tmp_path, monkeypatch):
    """The comparator case: 0 recorded, 26 excluded, and it must not read as empty."""
    import sorrydb.database.build_database as bd

    init_db = tmp_path / "init_db.json"
    _write_init_db(init_db, (REPO_A,))
    report = tmp_path / "report.md"

    monkeypatch.setattr(bd, "remote_heads_hash", lambda url, all_branches=False: "h")
    monkeypatch.setattr(
        bd,
        "leaf_commits",
        lambda url, all_branches=False: [
            {"sha": COMMIT_A, "branch": "main", "date": "2026-08-26T00:00:00+00:00"}
        ],
    )

    def extract_all_excluded(repo_url, branch, commit_sha, lean_data):
        return {
            "metadata": {"lean_version": "v4.24.0", "undetermined_type_excluded": 26},
            "sorries": [],
        }

    stats = update_database(
        init_db,
        tmp_path / "out.json",
        report_file=report,
        extract=extract_all_excluded,
    )

    # the commit is recorded with zero sorries and all 26 exclusions, so the
    # difference from a genuinely sorry free repo is on the page
    counts = stats[REPO_A]["counts"][COMMIT_A]
    assert counts["count"] == 0
    assert counts["undetermined_type_excluded"] == 26
    assert "**Sorries excluded, type undetermined:** 26" in report.read_text()

    # not treated as a failure, so the watermark advances and it is not retried
    repo = json.loads((tmp_path / "out.json").read_text())["repos"][0]
    assert repo["remote_heads_hash"] == "h"
    assert repo["last_time_visited"] != "2026-08-25T00:00:00+00:00"
    assert stats[REPO_A]["lake_timeout"] is None


def test_a_listing_failure_does_not_advance_the_watermark(tmp_path, monkeypatch):
    """A transient clone failure must not look like a repo with no branches.

    leaf_commits used to swallow every exception and return [], so the crawl
    advanced past a head it had never looked at and never came back to it.
    """
    import sorrydb.database.build_database as bd

    init_db = tmp_path / "init_db.json"
    _write_init_db(init_db, (REPO_A,))
    write_db = tmp_path / "out.json"

    # the remote reports a new head, so there is something to crawl
    monkeypatch.setattr(bd, "remote_heads_hash", lambda url, all_branches=False: "new")

    def failing_leaf_commits(url, all_branches=False):
        raise RuntimeError("[Errno 8] nodename nor servname provided")

    monkeypatch.setattr(bd, "leaf_commits", failing_leaf_commits)

    def extract_must_not_run(*args):
        raise AssertionError("nothing should be extracted")

    update_database(init_db, write_db, extract=extract_must_not_run)

    repo = json.loads(write_db.read_text())["repos"][0]
    assert repo["remote_heads_hash"] is None
    assert repo["last_time_visited"] == "2026-08-25T00:00:00+00:00"


def test_an_empty_branch_list_still_advances(tmp_path, monkeypatch):
    """The counterpart: genuinely nothing to crawl is not a failure."""
    import sorrydb.database.build_database as bd

    init_db = tmp_path / "init_db.json"
    _write_init_db(init_db, (REPO_A,))
    write_db = tmp_path / "out.json"

    monkeypatch.setattr(bd, "remote_heads_hash", lambda url, all_branches=False: "new")
    monkeypatch.setattr(bd, "leaf_commits", lambda url, all_branches=False: [])

    update_database(init_db, write_db, extract=lambda *a: None)

    repo = json.loads(write_db.read_text())["repos"][0]
    assert repo["remote_heads_hash"] == "new"
    assert repo["last_time_visited"] != "2026-08-25T00:00:00+00:00"


def test_repl_tag_lookup_failure_skips_the_prefilter(monkeypatch):
    """Fail open, as the docstring promises, instead of killing the run."""
    import sorrydb.database.build_database as bd

    def failing_repl_tags():
        raise RuntimeError("ls-remote failed")

    monkeypatch.setattr(bd, "repl_tags", failing_repl_tags)

    assert bd.unsupported_toolchain_repos(["a", "b"], resolve=lambda url: None) == {}


def test_an_empty_repl_tag_list_is_an_error_not_a_verdict(monkeypatch):
    """Otherwise all 424 repos are 'unsupported' and the run reports success."""
    import sorrydb.database.build_database as bd

    monkeypatch.setattr(bd, "repl_tags", lambda: ())

    resolved = {"a": "leanprover/lean4:v4.33.0", "b": "leanprover/lean4:v4.20.0"}
    assert bd.unsupported_toolchain_repos(list(resolved), resolve=resolved.get) == {}


# --- activity eligibility ----------------------------------------------------
#
# The database holds the whole universe that met the inclusion criteria, and
# whether a repo is worth crawling tonight is a verdict recomputed each run. A
# repo that goes quiet keeps its record and its watermark.

RECENT = "2026-09-01T00:00:00+00:00"
ANCIENT = "2024-01-01T00:00:00+00:00"


def _repo(url, **fields):
    record = {"remote_url": url, "stars": 100, "last_activity": RECENT}
    record.update(fields)
    return record


def test_eligibility_decisions():
    from sorrydb.database.build_database import ineligible_reason

    assert ineligible_reason(_repo("a")) is None
    assert "fewer than 10 stars" in ineligible_reason(_repo("a", stars=3))
    assert "no activity" in ineligible_reason(_repo("a", last_activity=ANCIENT))
    assert "opted out" in ineligible_reason(_repo("a", opted_out=True))

    # opting out wins over otherwise perfect metadata
    assert "opted out" in ineligible_reason(_repo("a", stars=9999, opted_out=True))

    # unknown metadata is not a verdict: the repo met the inclusion criteria,
    # and a missing star count means we failed to look
    assert ineligible_reason(_repo("a", stars=None, last_activity=None)) is None
    assert ineligible_reason(_repo("a", last_activity="not a date")) is None


def test_refresh_eligibility_uses_fresh_metadata_and_keeps_opt_out():
    from sorrydb.database.build_database import refresh_eligibility

    repos = [
        _repo("keeps", stars=3),  # stored metadata says too few stars
        _repo("drops", stars=100),
        _repo("opted", opted_out=True),
    ]

    def fetch_metadata(urls):
        assert set(urls) == {"keeps", "drops", "opted"}
        return {
            "keeps": {"stars": 50, "last_activity": RECENT},  # grew, now eligible
            "drops": {"stars": 1, "last_activity": RECENT},  # shrank
            "opted": {"stars": 9999, "last_activity": RECENT, "opted_out": False},
        }

    counts = refresh_eligibility(repos, fetch_metadata)

    by_url = {r["remote_url"]: r for r in repos}
    assert by_url["keeps"]["eligible"] is True
    assert by_url["drops"]["eligible"] is False
    assert by_url["drops"]["ineligible_reason"] == "fewer than 10 stars"

    # the refresh must never clear a hand set opt out
    assert by_url["opted"]["opted_out"] is True
    assert by_url["opted"]["eligible"] is False

    assert counts == {
        "fewer than 10 stars": 1,
        "opted out by the repository owner": 1,
    }


def test_a_metadata_refresh_failure_falls_back_to_stored_metadata():
    """A failed lookup must not read as a verdict, which would empty the index."""
    from sorrydb.database.build_database import refresh_eligibility

    repos = [_repo("a"), _repo("b", stars=2)]

    def failing_fetch(urls):
        raise RuntimeError("GraphQL is down")

    counts = refresh_eligibility(repos, failing_fetch)

    # decided from the stored metadata, not marked ineligible wholesale
    assert repos[0]["eligible"] is True
    assert repos[1]["eligible"] is False
    assert counts == {"fewer than 10 stars": 1}

    # a lookup that returns nothing is the same kind of failure
    assert refresh_eligibility(repos, lambda urls: {}) == counts
    assert repos[0]["eligible"] is True


def test_an_ineligible_repo_is_never_listed_and_keeps_its_watermark(
    tmp_path, monkeypatch
):
    import sorrydb.database.build_database as bd

    init_db = tmp_path / "init_db.json"
    init_db.write_text(
        json.dumps(
            {
                "repos": [
                    {
                        "remote_url": REPO_A,
                        "last_time_visited": "2026-08-25T00:00:00+00:00",
                        "remote_heads_hash": None,
                        "stars": 100,
                        "last_activity": RECENT,
                    },
                    {
                        "remote_url": REPO_B,
                        "last_time_visited": "2026-08-25T00:00:00+00:00",
                        "remote_heads_hash": None,
                        "stars": 1,  # too few
                        "last_activity": RECENT,
                    },
                ],
                "sorries": [],
            }
        )
    )
    write_db = tmp_path / "out.json"
    report = tmp_path / "report.md"

    listed = []

    def fake_leaf_commits(url, all_branches=False):
        listed.append(url)
        return [{"sha": COMMIT_A, "branch": "main", "date": "2026-08-26T00:00:00+00:00"}]

    monkeypatch.setattr(bd, "remote_heads_hash", lambda url, all_branches=False: "h")
    monkeypatch.setattr(bd, "leaf_commits", fake_leaf_commits)

    extracted = []

    def fake_extract(repo_url, branch, commit_sha, lean_data):
        extracted.append(repo_url)
        return {"metadata": {"lean_version": "v4.17.0"}, "sorries": [_fake_sorry(4)]}

    stats = update_database(
        init_db, write_db, report_file=report, extract=fake_extract
    )

    assert listed == [REPO_A]
    assert extracted == [REPO_A]

    repos = {r["remote_url"]: r for r in json.loads(write_db.read_text())["repos"]}
    assert repos[REPO_B]["last_time_visited"] == "2026-08-25T00:00:00+00:00"
    assert repos[REPO_B]["remote_heads_hash"] is None
    assert repos[REPO_B]["eligible"] is False

    # recorded separately from the toolchain skip, and not as a failure
    assert "fewer than 10 stars" in stats[REPO_B]["ineligible"]
    assert "unsupported_toolchain" not in stats[REPO_B]
    assert stats[REPO_B]["lake_timeout"] is None

    report_text = report.read_text()
    assert "**Repositories ineligible to crawl:** 1" in report_text
    assert "| fewer than 10 stars | 1 |" in report_text


def test_ineligibility_reasons_group_instead_of_fragmenting():
    """Reasons are report grouping keys, so they must not embed per-repo numbers."""
    from sorrydb.database.build_database import refresh_eligibility

    # ten repos, every one a different star count and a different stale date
    repos = [
        _repo(f"r{i}", stars=i, last_activity=f"2024-0{i % 9 + 1}-01T00:00:00+00:00")
        for i in range(10)
    ]

    counts = refresh_eligibility(repos, None)

    # one row, not ten
    assert counts == {"fewer than 10 stars": 10}
