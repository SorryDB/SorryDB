from sorrydb.agents.leaderboard_agent import LeaderboardAgent
from sorrydb.agents.rfl_strategy import RflStrategy


def test_leaderboard_agent_load(tmp_path):
    lean_data = tmp_path / "lean_data"

    LeaderboardAgent("test_rfl_leaderboard_agent", RflStrategy(), lean_data)

    # leaderboard_agent.request_challenge()
