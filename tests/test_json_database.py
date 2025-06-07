from sorrydb.database.sorry_database import JsonDatabase
from tests.mock_sorries import sorry_with_defaults


def test_json_database_load_database(update_db_single_test_repo_path):
    database = JsonDatabase()
    database.load_database(update_db_single_test_repo_path)


def test_json_database_add_sorry(update_db_single_test_repo_path):
    database = JsonDatabase()
    database.load_database(update_db_single_test_repo_path)

    length_before_add = len(database.sorries)

    database.add_sorry(sorry_with_defaults())

    length_after_add = len(database.sorries)

    assert (length_after_add - length_before_add) == 1


def test_json_database_aggregate_update_stats(update_db_single_test_repo_path):
    database = JsonDatabase()
    database.load_database(update_db_single_test_repo_path)

    database.add_sorry(sorry_with_defaults())

    aggregate_update_stats = database.aggregate_update_stats()

    assert aggregate_update_stats == (0, 0, 1, 1)


def test_calculate_human_readable_processing_time():
    assert (
        JsonDatabase._calculate_human_readable_processing_time(
            "2023-10-26T10:00:00", "2023-10-26T10:00:30"
        )
        == "30s"
    )
    assert (
        JsonDatabase._calculate_human_readable_processing_time(
            "2023-10-26T10:00:00", "2023-10-26T10:02:30"
        )
        == "2m 30s"
    )
    assert (
        JsonDatabase._calculate_human_readable_processing_time(
            "2023-10-26T10:00:00", "2023-10-26T11:05:15"
        )
        == "1h 5m 15s"
    )
    assert (
        JsonDatabase._calculate_human_readable_processing_time(
            "2023-10-26T10:00:00", "2023-10-26T10:00:00"
        )
        == "0s"
    )
