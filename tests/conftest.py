import json
from pathlib import Path

import pytest


@pytest.fixture
def mock_repos() -> list:
    """
    Returns a list of repository dictionaries from the mock_repos.json file.

    Each dictionary contains repository information such as the remote URL.
    """
    mock_repos_path = Path(__file__).parent / "mock_repo_lists" / "mock_repos.json"
    with open(mock_repos_path, "r") as f:
        data = json.load(f)
    return data["repos"]


@pytest.fixture
def init_db_mock_repos_path() -> Path:
    """
    init_db_mock_repos.json represents a database state after running `init_db`
    on init_db_single_test_repo.json
    """
    return Path(__file__).parent / "mock_databases" / "init_db_mock_repos.json"


@pytest.fixture
def init_db_mock_single_path() -> Path:
    """
    Returns the path to the update_database_single_test_repo.json test database file.

    update_database_single_test_repo.json represents a database state after running `update_database`
    on init_db_single_test_repo.json
    """
    return Path(__file__).parent / "mock_databases" / "init_db_mock_single.json"


@pytest.fixture
def update_db_single_test_repo_path() -> Path:
    """
    update_database_single_test_repo.json represents a database state after running `update_database`
    on init_db_mock_single.json
    """
    return (
        Path(__file__).parent
        / "mock_databases"
        / "update_database_single_test_repo.json"
    )


@pytest.fixture
def init_db_mock_multiple_repos_path() -> Path:
    """
    init_db_mock_multiple_repos.json represents a database state after running `init_db`
    on mock_repos.json
    """
    return Path(__file__).parent / "mock_databases" / "init_db_mock_multiple_repos.json"


@pytest.fixture
def update_db_multiple_repos_test_repo_path() -> Path:
    """
    Returns the path to the update_database_single_test_repo.json test database file.

    update_db_multiple_repos_test_repo.json represents a database state after running `update_database`
    on init_db_mock_multiple_repos.json
    """
    return (
        Path(__file__).parent
        / "mock_databases"
        / "update_database_multiple_repos_test_repo.json"
    )


@pytest.fixture
def deduplicated_update_db_single_test_path() -> Path:
    """
    Returns the path to the deduplicated_update_db_single_test.json test query results filefile.

    deduplicated_update_db_single_test.json represents a database state after running `query_database`
    with the deduplicate sorries by goal query on update_database_single_test_repo.json
    """
    return (
        Path(__file__).parent
        / "mock_query_results"
        / "deduplicated_update_db_single_test_repo.json"
    )


@pytest.fixture
def mock_sorry() -> Path:
    """
    Returns the path to the mock_sorry.json test query results filefile.
    """
    return Path(__file__).parent / "mock_sorries" / "mock_sorry.json"


@pytest.fixture
def leaderboard_credentials(monkeypatch):
    """
    Sets up leaderboard authentication environment variables for testing.

    Uses the same credentials as the test_user fixture in tests/leaderboard/conftest.py
    for consistency across the test suite.

    Returns:
        dict: Dictionary with 'username' and 'password' keys
    """
    import os

    # Default to port 8080 (compose.yml deployment), but allow override
    default_host = "http://127.0.0.1:8080"

    credentials = {
        "username": "test@example.com",
        "password": "testpass123",
        "host": os.getenv("LEADERBOARD_HOST", default_host)
    }

    monkeypatch.setenv("LEADERBOARD_USERNAME", credentials["username"])
    monkeypatch.setenv("LEADERBOARD_PASSWORD", credentials["password"])
    monkeypatch.setenv("LEADERBOARD_HOST", credentials["host"])

    return credentials


@pytest.fixture
def leaderboard_test_user(leaderboard_credentials):
    """
    Ensures the test user is registered on the leaderboard API server.

    This fixture attempts to register the test user. If the user already exists
    (409 Conflict), it silently continues. This allows tests to run without
    manual user setup.

    Requires a running leaderboard API server at LEADERBOARD_HOST.

    Returns:
        dict: The credentials dictionary
    """
    import requests

    host = leaderboard_credentials["host"]
    username = leaderboard_credentials["username"]
    password = leaderboard_credentials["password"]

    try:
        response = requests.post(
            f"{host}/auth/register",
            json={"email": username, "password": password},
            timeout=2
        )
        # 201 = created, 409 = already exists (both are OK)
        if response.status_code not in [201, 409]:
            pytest.skip(f"Failed to register test user: {response.status_code}")
    except (requests.ConnectionError, requests.Timeout) as e:
        pytest.skip(f"Could not connect to leaderboard API: {e}")

    return leaderboard_credentials
