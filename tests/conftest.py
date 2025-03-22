import json
import pytest
from pathlib import Path


@pytest.fixture
def init_db_single_test_repo_path() -> Path:
    """
    The path to the init_db_single_test_repo.json test database file.

    init_db_single_test_repo.json is the initial database created by running `init_database`
    on a single test repo.
    """
    return Path(__file__).parent / "mock_databases" / "init_db_single_test_repo.json"

@pytest.fixture
def update_db_single_test_repo_path() -> Path:
    """
    Returns the path to the update_database_single_test_repo.json test database file.

    update_database_single_test_repo.json represents a database state after running `update_database`
    on init_db_single_test_repo.json 
    """
    return Path(__file__).parent / "mock_databases" / "update_database_single_test_repo.json"

@pytest.fixture
def init_db_mock_repos_path() -> Path:
    """
    Returns the path to the update_database_single_test_repo.json test database file.

    update_database_single_test_repo.json represents a database state after running `update_database`
    on init_db_single_test_repo.json 
    """
    return Path(__file__).parent / "mock_databases" / "init_db_mock_repos.json"


@pytest.fixture
def mock_repos() -> list:
    """
    Returns a list of repository dictionaries from the mock_repos.json file.
    
    Each dictionary contains repository information such as the remote URL.
    """
    mock_repos_path = Path(__file__).parent.parent / "repo_lists" / "mock_repos.json"
    with open(mock_repos_path, "r") as f:
        data = json.load(f)
    return data["repos"]



