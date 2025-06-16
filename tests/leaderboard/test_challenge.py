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


def test_get_agent_challenges_paginated():
    agent_id = _create_agent(client)

    # Create 5 challenges for the agent
    challenge_ids = []
    for _ in range(5):
        response = client.post(f"/agents/{agent_id}/challenges")
        assert response.status_code == 201
        challenge_ids.append(response.json()["id"])

    # Get first 2 challenges
    response = client.get(f"/agents/{agent_id}/challenges/?skip=0&limit=2")
    assert response.status_code == 200
    challenges = response.json()
    assert len(challenges) == 2
    assert challenges[0]["id"] == challenge_ids[0]
    assert challenges[1]["id"] == challenge_ids[1]

    # Get next 2 challenges
    response = client.get(f"/agents/{agent_id}/challenges/?skip=2&limit=2")
    assert response.status_code == 200
    challenges = response.json()
    assert len(challenges) == 2
    assert challenges[0]["id"] == challenge_ids[2]
    assert challenges[1]["id"] == challenge_ids[3]

    # Get last challenge
    response = client.get(f"/agents/{agent_id}/challenges/?skip=4&limit=2")
    assert response.status_code == 200
    challenges = response.json()
    assert len(challenges) == 1
    assert challenges[0]["id"] == challenge_ids[4]

    # Skip beyond available challenges
    response = client.get(f"/agents/{agent_id}/challenges/?skip=5&limit=2")
    assert response.status_code == 200
    challenges = response.json()
    assert len(challenges) == 0

    # Default pagination (skip=0, limit=10 by default in API)
    response = client.get(f"/agents/{agent_id}/challenges/")
    assert response.status_code == 200
    challenges = response.json()
    assert len(challenges) == 5  # Assuming default limit is >= 5


def test_get_challenges_for_non_existent_agent():
    non_existent_agent_id = "non_existent_agent"
    response = client.get(f"/agents/{non_existent_agent_id}/challenges/?skip=0&limit=2")
    assert response.status_code == 404
