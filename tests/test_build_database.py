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
            "repl_timeout": None,
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
            "repl_timeout": None,
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
            "repl_timeout": None,
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
