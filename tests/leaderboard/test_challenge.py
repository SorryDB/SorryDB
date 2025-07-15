from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session

from sorrydb.agents.json_agent import load_sorry_json
from sorrydb.leaderboard.database.postgres_database import SQLDatabase
from sorrydb.leaderboard.model.challenge import ChallengeStatus
from sorrydb.leaderboard.model.sorry import SQLSorry


def _select_sample_sorry() -> SQLSorry:
    """
    Test sorry selector which returns a sample sorry from the `sample_sorry_list.json`
    """
    # TODO: This is a hack. If we want to serve sample sorries we should move them into the `leaderboard` module
    project_root = Path(__file__).resolve().parent.parent.parent
    sample_sorries_path = project_root / "doc" / "sample_sorry_list.json"
    sample_sorries = load_sorry_json(json_path=sample_sorries_path)
    return SQLSorry.from_json_sorry(sample_sorries[0])


def _create_agent(client: TestClient) -> str:
    """Helper function to create an agent and return its ID."""
    response = client.post("/agents/", json={"name": "test agent"})
    assert response.status_code == 201
    agent = response.json()
    return agent["id"]


def _add_test_sorry(session: Session):
    test_sorry = _select_sample_sorry()
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

    new_challenge_response = client.post(f"/agents/{agent_id}/challenges")
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


def test_challenge_agent_relationship(session: Session, client: TestClient):
    _add_test_sorry(session)
    agent_id = _create_agent(client)

    # Create a challenge for the agent
    response = client.post(f"/agents/{agent_id}/challenges")
    assert response.status_code == 201
    challenge_id = response.json()["id"]

    # Fetch the challenge from the database and verify the agent relationship
    db = SQLDatabase(session)
    challenge = db.get_challenge(challenge_id)
    assert challenge is not None
    assert challenge.agent is not None
    assert challenge.agent.id == agent_id


def test_agent_challenges_relationship(session: Session, client: TestClient):
    _add_test_sorry(session)
    agent_id = _create_agent(client)

    # Create multiple challenges for the agent
    challenge_ids = set()
    for _ in range(3):
        response = client.post(f"/agents/{agent_id}/challenges")
        assert response.status_code == 201
        challenge_ids.add(response.json()["id"])

    # Fetch the agent from the database and verify the challenges relationship
    db = SQLDatabase(session)
    agent = db.get_agent(agent_id)
    assert agent is not None
    assert len(agent.challenges) == 3

    # Verify that the agent's challenges list contains the correct challenge IDs
    fetched_challenge_ids = {c.id for c in agent.challenges}
    assert fetched_challenge_ids == challenge_ids
