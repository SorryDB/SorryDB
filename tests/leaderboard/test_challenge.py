from fastapi.testclient import TestClient

from sorrydb.leaderboard.api.app import app

client = TestClient(app)


def _create_agent(client: TestClient) -> str:
    """Helper function to create an agent and return its ID."""
    response = client.post("/agents/", json={"name": "test agent"})
    assert response.status_code == 201
    agent = response.json()
    return agent["id"]


def test_create_challenge():
    agent_id = _create_agent(client)

    new_challenge_response = client.post(f"/agents/{agent_id}/challenges")
    assert new_challenge_response.status_code == 201
    assert "id" in new_challenge_response.json()


def test_submit_challenge():
    agent_id = _create_agent(client)

    new_challenge_response = client.post(f"/agents/{agent_id}/challenges")
    assert new_challenge_response.status_code == 201

    new_challenge_response_json = new_challenge_response.json()
    challenge_id = new_challenge_response_json["id"]

    submit_challenge_response = client.post(
        f"/agents/{agent_id}/challenges/{challenge_id}/submit", json={"proof": "rfl"}
    )

    assert submit_challenge_response.status_code == 200
