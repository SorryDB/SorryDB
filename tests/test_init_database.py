import datetime
import json

from sorrydb.database.build_database import init_database


def test_init_database_with_mock_repos(mock_repos, init_db_mock_repos_path, tmp_path):
    """
    Test that init_database correctly initializes a database with mock repositories.
    """
    temp_db_path = tmp_path / "test_database.json"

    # Initialize the database
    init_database(
        [repo["remote"] for repo in mock_repos],  # repo urls
        datetime.datetime(2025, 3, 10, tzinfo=datetime.timezone.utc),  # fixed test date
        temp_db_path,
    )

    # Load the generated database
    with open(temp_db_path, "r") as f:
        generated_db = json.load(f)

    # Load the expected database
    with open(init_db_mock_repos_path, "r") as f:
        expected_db = json.load(f)

    assert generated_db == expected_db, (
        "Generated database does not match expected database"
    )
