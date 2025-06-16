import pytest

from sorrydb.leaderboard.api.app_config import get_repository


@pytest.fixture(autouse=True)
def reset_in_memory_db():
    db = get_repository()
    db.agents.clear()
    db.challenges.clear()
