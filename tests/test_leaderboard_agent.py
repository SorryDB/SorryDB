import pytest
import requests

from sorrydb.runners.leaderboard_runner import LeaderboardRunner
from sorrydb.runners.rfl_strategy import RflStrategy


def is_leaderboard_server_running(host="http://127.0.0.1:8080"):
    """Check if the leaderboard API server is running."""
    try:
        response = requests.get(f"{host}/docs", timeout=1)
        return response.status_code == 200
    except (requests.ConnectionError, requests.Timeout):
        return False


@pytest.mark.skipif(
    not is_leaderboard_server_running(),
    reason="Leaderboard API server must be running at http://127.0.0.1:8080",
)
def test_leaderboard_agent_load(tmp_path, leaderboard_test_user):
    """Test leaderboard agent with authentication.

    This test requires a running leaderboard API server at http://127.0.0.1:8080.

    The leaderboard_test_user fixture automatically:
    - Sets up environment variables (LEADERBOARD_USERNAME, LEADERBOARD_PASSWORD, LEADERBOARD_HOST)
    - Registers the test user (test@example.com / testpass123) if not already registered
    - Uses credentials consistent with other leaderboard API tests

    To run this test:
    1. Start the leaderboard API server: docker compose -f leaderboard_deployment/compose.yml up
       OR: poetry run uvicorn sorrydb.leaderboard.api.app:app --port 8080
    2. Run: poetry run pytest tests/test_leaderboard_agent.py

    The test user will be automatically registered on first run.
    """
    lean_data = tmp_path / "lean_data"

    leaderboard_agent = LeaderboardRunner(
        "test_rfl_leaderboard_agent", RflStrategy(), lean_data
    )

    leaderboard_agent.attempt_challenge()
    pass
