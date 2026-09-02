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

    assert aggregate_update_stats == (0, 0, 1, 1, 0)


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


def test_write_database_leaves_the_old_file_intact_if_the_write_fails(tmp_path):
    """The crawl checkpoints hundreds of times a run and Cloud Run SIGKILLs.

    Streaming into the live path left a truncated database that the next run
    could not load, so the write goes to a sibling and is renamed.
    """
    import json as json_module

    import pytest

    from sorrydb.database import sorry_database

    target = tmp_path / "sorry_database.json"
    target.write_text('{"repos": [], "sorries": []}')
    original = target.read_text()

    database = JsonDatabase()
    database.load_database(target)

    def explode(*args, **kwargs):
        raise OSError("killed mid write")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(sorry_database.json, "dump", explode)
    try:
        with pytest.raises(OSError):
            database.write_database(target)
    finally:
        monkeypatch.undo()

    # the live database is untouched and still loadable
    assert target.read_text() == original
    json_module.loads(target.read_text())

    # a successful write replaces it and leaves no temp file behind
    database.write_database(target)
    assert json_module.loads(target.read_text()) == {"repos": [], "sorries": []}
    assert list(tmp_path.iterdir()) == [target]
