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
    """Assert a crawl of the local Lean fixture produced what the REPL finds."""
    remote = str(repo_path)
    expected = expected_fixture_sorries()

    sorries = [s for s in database["sorries"] if s["repo"]["remote"] == remote]
    assert {_location_key(s["location"], s["debug_info"]["goal"]) for s in sorries} == (
        expected
    )

    for sorry in sorries:
        assert sorry["repo"]["branch"] == FIXTURE_BRANCH
        assert sorry["repo"]["commit"] == head_sha
        assert sorry["repo"]["lean_version"] == fixture_lean_version()
        assert sorry["debug_info"]["url"] == (
            f"{remote}/blob/{head_sha}/{sorry['location']['path']}"
            f"#L{sorry['location']['start_line']}"
        )
        # git blame ran against the fixture commit
        assert sorry["metadata"]["blame_date"] == FIXTURE_BLAME_DATE
        assert sorry["metadata"]["blame_email_hash"] == (
            hashlib.sha256(FIXTURE_EMAIL.encode()).hexdigest()[:12]
        )

    repo_stats = update_stats[remote]
    assert repo_stats["new_leaf_commit"] is True
    assert repo_stats["lake_timeout"] is None
    assert set(repo_stats["counts"]) == {head_sha}
    assert repo_stats["counts"][head_sha]["count"] == len(expected)

    repo_entry = next(r for r in database["repos"] if r["remote_url"] == remote)
    assert repo_entry["remote_heads_hash"] == remote_heads_hash(
        remote, all_branches=False
    )


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

    # count_new_goal counts each goal once, and the fixture repeats some
    goals = {goal for *_, goal in expected_fixture_sorries()}
    assert update_stats[str(repo_path)]["counts"][head_sha]["count_new_goal"] == len(
        goals
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

    expected = expected_fixture_sorries()
    assert len(database["sorries"]) == 2 * len(expected)

    # Sorry ids include the remote, so the same sorry in two repos is two rows
    assert len({s["id"] for s in database["sorries"]}) == 2 * len(expected)

    # Goals are deduplicated across the whole database, so the second repo
    # contributes no new ones
    goals = {goal for *_, goal in expected}
    assert update_stats[str(repo_a)]["counts"][sha_a]["count_new_goal"] == len(goals)
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
