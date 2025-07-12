from fastapi.testclient import TestClient
from sqlmodel import Session

from sorrydb.leaderboard.database.postgres_database import SQLDatabase
from sorrydb.leaderboard.model.challenge import ChallengeStatus
from sorrydb.leaderboard.services.sorry_selector_service import select_sample_sorry


def _create_agent(client: TestClient) -> str:
    """Helper function to create an agent and return its ID."""
    response = client.post("/agents/", json={"name": "test agent"})
    assert response.status_code == 201
    agent = response.json()
    return agent["id"]


def _add_test_sorry(session: Session):
    test_sorry = select_sample_sorry()
    session.add(test_sorry)
    session.commit()


def test_create_challenge(session, client):
    _add_test_sorry(session)
    agent_id = _create_agent(client)

    new_challenge_response = client.post(f"/agents/{agent_id}/challenges")
    assert new_challenge_response.status_code == 201
    assert "id" in new_challenge_response.json()


def test_submit_challenge(session: Session, client: TestClient):
    _add_test_sorry(session)
    agent_id = _create_agent(client)

    new_challenge_response = client.post(f"/agents/{agent_id}/challenges/")
    assert new_challenge_response.status_code == 201
    challenge_id = new_challenge_response.json()["id"]

    proof_text = "this is my proof"
    submit_challenge_response = client.post(
        f"/agents/{agent_id}/challenges/{challenge_id}/submit/",
        json={"proof": proof_text},
    )

    assert submit_challenge_response.status_code == 200
    submitted_challenge = submit_challenge_response.json()
    assert submitted_challenge["status"] == ChallengeStatus.PENDING_VERIFICATION.value
    assert submitted_challenge["submission"] == proof_text

    # Verify the update in the database
    db = SQLDatabase(session)
    challenge = db.get_challenge(challenge_id)
    assert challenge is not None
    assert challenge.status == ChallengeStatus.PENDING_VERIFICATION
    assert challenge.submission == proof_text


def test_get_agent_challenges_paginated(session, client):
    _add_test_sorry(session)
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


def test_get_challenges_for_non_existent_agent(client):
    non_existent_agent_id = "non_existent_agent"
    response = client.get(f"/agents/{non_existent_agent_id}/challenges/?skip=0&limit=2")
    assert response.status_code == 404
