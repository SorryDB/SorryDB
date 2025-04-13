import json

from sorrydb.database.query_database import deduplicate_sorries_by_goal, query_database
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


def test_query_database_single_test_repo(
    update_db_single_test_repo_path, deduplicated_update_db_single_test_path, tmp_path
):
    tmp_write_query_results = tmp_path / "deduplicated_query_results.json"

    deduplicated_sorries = query_database(
        database_path=update_db_single_test_repo_path,
        query_results_path=tmp_write_query_results,
    )

    assert deduplicated_sorries is not None

    with (
        open(tmp_write_query_results, "r") as f1,
        open(deduplicated_update_db_single_test_path, "r") as f2,
    ):
        query_reults_json = json.load(f1)
        expected_query_reults_json = json.load(f2)

    assert query_reults_json == expected_query_reults_json
