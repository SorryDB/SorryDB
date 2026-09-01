import json

import pytest

from sorrydb.database.build_database import (
    prepare_and_process_lean_repo,
    update_database,
)


def test_prepare_and_process_lean_repo_with_mutiple_lean_versions(tmp_path):
    """
    Verify that the database builder can handle repositories
    that use different versions of Lean.

    sorryClientTestRepoMath uses v4.17.0-rc1 and sorryClientTestRepo uses v4.16.0
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


def normalize_sorrydb_for_comparison(data):
    """Normalize run-specific timestamps in database to allow comparison across runs."""
    for repo in data.get("repos", []):
        repo["last_time_visited"] = "NORMALIZED_TIMESTAMP"

    for sorry in data.get("sorries", []):
        sorry["metadata"]["inclusion_date"] = "NORMALIZED_TIMESTAMP"

    return data


def normalize_update_stats_for_comparison(update_stats):
    """Normalize timestamps in update_stats dictionary in place."""
    for repo_url, repo_data in update_stats.items():
        repo_data["start_processing_time"] = "NORMALIZED_TIMESTAMP"
        repo_data["end_processing_time"] = "NORMALIZED_TIMESTAMP"
        repo_data["total_processing_time"] = "NORMALIZED_TIMESTAMP"
    return update_stats


@pytest.mark.parametrize(
    "use_lean_data_dir",
    [False, True],
    ids=["without_lean_data_dir", "with_lean_data_dir"],
)
def test_update_database_single_repo(
    init_db_mock_single_path,
    update_db_single_test_repo_path,
    tmp_path,
    use_lean_data_dir,
):
    """Test that update_database correctly updates the database file,
    optionally using a lean_data directory."""

    tmp_write_db = tmp_path / "updated_sorry_database.json"
    lean_data_arg = None

    if use_lean_data_dir:
        lean_data_arg = tmp_path / "lean_data"

    update_stats = update_database(
        init_db_mock_single_path, tmp_write_db, lean_data_path=lean_data_arg
    )

    normalized_stats = normalize_update_stats_for_comparison(update_stats)

    expected_stats = {
        "https://github.com/austinletson/sorryClientTestRepo": {
            "counts": {
                "78202012bfe87f99660ba2fe5973eb1a8110ab64": {
                    "count": 3,
                    "count_new_goal": 2,
                },
                "f8632a130a6539d9f546a4ef7b412bc3d86c0f63": {
                    "count": 4,
                    "count_new_goal": 1,
                },
            },
            "new_leaf_commit": True,
            "start_processing_time": "NORMALIZED_TIMESTAMP",
            "end_processing_time": "NORMALIZED_TIMESTAMP",
            "total_processing_time": "NORMALIZED_TIMESTAMP",
            "lake_timeout": None,
        }
    }

    assert normalized_stats == expected_stats

    assert tmp_write_db.exists(), "The updated database file was not created"

    with (
        open(tmp_write_db, "r") as f1,
        open(update_db_single_test_repo_path, "r") as f2,
    ):
        tmp_content = json.load(f1)
        expected_content = json.load(f2)

    # Normalize time fields and ids in both JSONs
    normalized_tmp = normalize_sorrydb_for_comparison(tmp_content)
    normalized_expected = normalize_sorrydb_for_comparison(expected_content)

    assert normalized_tmp == normalized_expected, (
        "The sorries data doesn't match the expected content"
    )


def test_update_database_multiple_repo(
    init_db_mock_multiple_repos_path, update_db_multiple_repos_test_repo_path, tmp_path
):
    """Test that update_database correctly updates the database file."""

    tmp_write_db = tmp_path / "updated_sorry_database.json"

    update_stats = update_database(init_db_mock_multiple_repos_path, tmp_write_db)

    normalized_stats = normalize_update_stats_for_comparison(update_stats)

    expected_stats = {
        "https://github.com/austinletson/sorryClientTestRepo": {
            "counts": {
                "78202012bfe87f99660ba2fe5973eb1a8110ab64": {
                    "count": 3,
                    "count_new_goal": 2,
                },
                "f8632a130a6539d9f546a4ef7b412bc3d86c0f63": {
                    "count": 4,
                    "count_new_goal": 1,
                },
            },
            "new_leaf_commit": True,
            "start_processing_time": "NORMALIZED_TIMESTAMP",
            "end_processing_time": "NORMALIZED_TIMESTAMP",
            "total_processing_time": "NORMALIZED_TIMESTAMP",
            "lake_timeout": None,
        },
        "https://github.com/austinletson/sorryClientTestRepoMath": {
            "counts": {
                "e853cb7ab1cdb382ea12b3f11bcbe6bbfeb32d47": {
                    "count": 1,
                    "count_new_goal": 1,
                },
                "c1c539f7432bafccd8eaf55f363eaad4e0b92374": {
                    "count": 2,
                    "count_new_goal": 1,
                },
            },
            "new_leaf_commit": True,
            "start_processing_time": "NORMALIZED_TIMESTAMP",
            "end_processing_time": "NORMALIZED_TIMESTAMP",
            "total_processing_time": "NORMALIZED_TIMESTAMP",
            "lake_timeout": None,
        },
    }

    assert normalized_stats == expected_stats

    assert tmp_write_db.exists(), "The updated database file was not created"

    with (
        open(tmp_write_db, "r") as f1,
        open(update_db_multiple_repos_test_repo_path, "r") as f2,
    ):
        tmp_content = json.load(f1)
        expected_content = json.load(f2)

    # Normalize time fields and ids in both JSONs
    normalized_tmp = normalize_sorrydb_for_comparison(tmp_content)
    normalized_expected = normalize_sorrydb_for_comparison(expected_content)

    assert normalized_tmp == normalized_expected, (
        "The sorries data doesn't match the expected content"
    )


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


def _write_init_db(path, repo_urls):
    path.write_text(
        json.dumps(
            {
                "repos": [
                    {
                        "remote_url": url,
                        "last_time_visited": "2026-08-25T00:00:00+00:00",
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

    monkeypatch.setattr(bd, "remote_heads_hash", lambda url: f"heads-{url[-1]}")
    monkeypatch.setattr(bd, "leaf_commits", lambda url: commits[url])

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
