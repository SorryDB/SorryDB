import json
from datetime import datetime, timedelta, timezone

from sorrydb.database.deduplicate_database import (
    deduplicate_database,
    deduplicate_sorries_by_goal,
    varied_repo_frequent_n_sorries,
)
from sorrydb.database.sorry_database import JsonDatabase
from tests.mock_sorries import FEB_1, JAN_1, JAN_15, sorry_with_defaults


def test_deduplicate_sorries_by_goal_empty_list():
    result = deduplicate_sorries_by_goal([])
    assert result == []


def test_deduplicate_sorries_by_goal_unique_goals():
    sorries = [
        sorry_with_defaults(goal="goal_1"),
        sorry_with_defaults(goal="goal_2"),
        sorry_with_defaults(goal="goal_3"),
    ]

    result = deduplicate_sorries_by_goal(sorries)
    assert len(result) == 3
    assert {s.debug_info.goal for s in result} == {"goal_1", "goal_2", "goal_3"}


def test_deduplicate_sorries_by_goal_duplicate_goals():
    sorries = [
        sorry_with_defaults(goal="goal_1", inclusion_date=JAN_1),
        sorry_with_defaults(goal="goal_1", inclusion_date=JAN_15),  # most recent
        sorry_with_defaults(goal="goal_2", inclusion_date=JAN_15),
        sorry_with_defaults(goal="goal_2", inclusion_date=FEB_1),  # most recent
    ]

    result = deduplicate_sorries_by_goal(sorries)
    assert len(result) == 2

    # Extract goals and dates for easier assertion
    result_map = {s.debug_info.goal: s.metadata.inclusion_date for s in result}

    assert result_map["goal_1"] == JAN_15
    assert result_map["goal_2"] == FEB_1


def test_deduplicate_database_single_test_repo(
    update_db_single_test_repo_path, deduplicated_update_db_single_test_path, tmp_path
):
    tmp_write_query_results = tmp_path / "deduplicated_query_results.json"

    deduplicated_sorries = deduplicate_database(
        database_path=update_db_single_test_repo_path,
        query_results_path=tmp_write_query_results,
    )

    assert deduplicated_sorries is not None

    with (
        open(tmp_write_query_results, "r") as f1,
        open(deduplicated_update_db_single_test_path, "r") as f2,
    ):
        query_results_json = json.load(f1)
        expected_query_results_json = json.load(f2)

    assert query_results_json == expected_query_results_json


def test_deduplicate_database_multiple_repos_with_max_sorries(
    update_db_multiple_repos_test_repo_path, tmp_path
):
    """Test that deduplicate_database with max_sorries limits the sorries
    and selects them from different repositories when possible."""
    tmp_write_query_results = tmp_path / "deduplicated_query_results_with_max.json"

    # Set max_sorries to a specific value
    max_sorries = 3

    # Call deduplicate_database with max_sorries parameter
    deduplicated_sorries = deduplicate_database(
        database_path=update_db_multiple_repos_test_repo_path,
        query_results_path=tmp_write_query_results,
        max_sorries=max_sorries,
    )

    assert deduplicated_sorries is not None

    # Verify the number of sorries doesn't exceed max_sorries
    assert len(deduplicated_sorries) <= max_sorries

    # Load the original database to verify varied repo selection
    database = JsonDatabase()
    database.load_database(update_db_multiple_repos_test_repo_path)
    original_sorries = database.get_sorries()

    # Get list of unique repos in original data
    original_repos = {sorry.repo.remote for sorry in original_sorries}

    # Verify the sorries come from different repos when possible
    result_repos = {sorry.repo.remote for sorry in deduplicated_sorries}
    assert len(result_repos) == min(len(original_repos), max_sorries)

    # Verify the sorries from json file match the returned sorries
    with open(tmp_write_query_results, "r") as f:
        query_results_json = json.load(f)

    expected_results = [
        {
            "repo": {
                "remote": "https://github.com/austinletson/sorryClientTestRepo",
                "branch": "master",
                "commit": "f8632a130a6539d9f546a4ef7b412bc3d86c0f63",
                "lean_version": "v4.16.0",
            },
            "location": {
                "start_line": 10,
                "start_column": 2,
                "end_line": 10,
                "end_column": 7,
                "file": "SorryClientTestRepo/BasicWithElabTactic.lean",
            },
            "debug_info": {
                "goal": "⊢ 1 + 4 = 5",
                "url": "https://github.com/austinletson/sorryClientTestRepo/blob/f8632a130a6539d9f546a4ef7b412bc3d86c0f63/SorryClientTestRepo/BasicWithElabTactic.lean#L10",
            },
            "metadata": {
                "blame_email_hash": "9fe2851ae6a7",
                "blame_date": "2025-03-13T06:55:53-04:00",
                "inclusion_date": "2025-03-27T22:13:52.041823+00:00",
            },
            "id": "32f0c31873bbf531a3e8b8b2bf6dd73f7e70c0525367f93a026ff36a95d5d49b",
        },
        {
            "repo": {
                "remote": "https://github.com/austinletson/sorryClientTestRepoMath",
                "branch": "some_branch",
                "commit": "c1c539f7432bafccd8eaf55f363eaad4e0b92374",
                "lean_version": "v4.17.0-rc1",
            },
            "location": {
                "start_line": 7,
                "start_column": 45,
                "end_line": 7,
                "end_column": 50,
                "file": "SorryClientTestRepoMath/WithImport.lean",
            },
            "debug_info": {
                "goal": "X : Type\ninst✝ : TopologicalSpace X\n⊢ IsClosed Set.univ",
                "url": "https://github.com/austinletson/sorryClientTestRepoMath/blob/c1c539f7432bafccd8eaf55f363eaad4e0b92374/SorryClientTestRepoMath/WithImport.lean#L7",
            },
            "metadata": {
                "blame_email_hash": "24b3fae77efa",
                "blame_date": "2025-03-07T20:58:44+01:00",
                "inclusion_date": "2025-03-27T22:15:37.775456+00:00",
            },
            "id": "e15435bd01ddd9ee04d31a1c72ea9acbefb78d542b1bf53991b8c93abba49943",
        },
        {
            "repo": {
                "remote": "https://github.com/austinletson/sorryClientTestRepo",
                "branch": "branch1",
                "commit": "78202012bfe87f99660ba2fe5973eb1a8110ab64",
                "lean_version": "v4.16.0",
            },
            "location": {
                "start_line": 11,
                "start_column": 2,
                "end_line": 11,
                "end_column": 7,
                "file": "SorryClientTestRepo/BasicWithElabTactic.lean",
            },
            "debug_info": {
                "goal": "⊢ 1 + 3 = 4",
                "url": "https://github.com/austinletson/sorryClientTestRepo/blob/78202012bfe87f99660ba2fe5973eb1a8110ab64/SorryClientTestRepo/BasicWithElabTactic.lean#L11",
            },
            "metadata": {
                "blame_email_hash": "9fe2851ae6a7",
                "blame_date": "2025-03-11T18:28:42-04:00",
                "inclusion_date": "2025-03-27T22:13:42.762667+00:00",
            },
            "id": "d4a88c0c3b53771bbdf3dea76fa3b1e3042921b49c1839060f9b3a9807a3cb9c",
        },
    ]

    assert query_results_json == expected_results


def test_varied_repo_frequent_n_sorries():
    """Test that varied_repo_frequent_n_sorries selects sorries from different
    repositories, prioritizing recent blame dates."""

    # Create base date for testing
    base_date = datetime(2023, 1, 1, tzinfo=timezone.utc)

    # Create sorries from three different repos with varying blame dates
    sorries = [
        # Repo 1 - three sorries with different dates
        sorry_with_defaults(
            goal="repo1_goal1", blame_date=base_date, repo_remote="repo1"
        ),
        sorry_with_defaults(
            goal="repo1_goal2",
            blame_date=base_date + timedelta(days=5),
            repo_remote="repo1",
        ),
        sorry_with_defaults(
            goal="repo1_goal3",
            blame_date=base_date + timedelta(days=10),  # Most recent for repo1
            repo_remote="repo1",
        ),
        # Repo 2 - two sorries with different dates
        sorry_with_defaults(
            goal="repo2_goal1",
            blame_date=base_date + timedelta(days=2),
            repo_remote="repo2",
        ),
        sorry_with_defaults(
            goal="repo2_goal2",
            blame_date=base_date + timedelta(days=7),  # Most recent for repo2
            repo_remote="repo2",
        ),
        # Repo 3 - one sorry
        sorry_with_defaults(
            goal="repo3_goal1",
            blame_date=base_date + timedelta(days=3),
            repo_remote="repo3",
        ),
    ]

    # Test with n=2 (should get one from repo1 and one from repo2, both the most recent)
    result = varied_repo_frequent_n_sorries(sorries, 2)
    assert len(result) == 2

    # Check that we got sorries from different repos
    result_repos = {sorry.repo.remote for sorry in result}
    assert len(result_repos) == 2

    # Verify we got the most recent sorry from each repo
    for repo in result_repos:
        repo_sorries = [s for s in sorries if s.repo.remote == repo]
        repo_sorry_in_result = [s for s in result if s.repo.remote == repo][0]
        most_recent_sorry = max(repo_sorries, key=lambda s: s.metadata.blame_date)
        assert repo_sorry_in_result.debug_info.goal == most_recent_sorry.debug_info.goal

    # Test with n=4 (should get one from each repo, then one more from repo1)
    result = varied_repo_frequent_n_sorries(sorries, 4)
    assert len(result) == 4

    # Check repo distribution
    repo_counts = {}
    for sorry in result:
        repo_counts[sorry.repo.remote] = repo_counts.get(sorry.repo.remote, 0) + 1

    # We should have all 3 repos represented
    assert len(repo_counts) == 3
    # Repo1 should have 2 sorries (since we need 4 total)
    assert repo_counts["repo1"] == 2
    # Repo2 and Repo3 should have 1 sorry each
    assert repo_counts["repo2"] == 1
    assert repo_counts["repo3"] == 1
