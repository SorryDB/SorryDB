from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session

from sorrydb.agents.json_agent import load_sorry_json
from sorrydb.leaderboard.database.postgres_database import SQLDatabase
from sorrydb.leaderboard.model.challenge import ChallengeStatus
from sorrydb.leaderboard.model.sorry import SQLSorry
from tests.mock_sorries import sorry_with_defaults


def _select_sample_sorry() -> SQLSorry:
    """
    Test sorry selector which returns a sample sorry from the `sample_sorry_list.json`
    """
    # TODO: This is a hack. If we want to serve sample sorries we should move them into the `leaderboard` module
    project_root = Path(__file__).resolve().parent.parent.parent
    sample_sorries_path = project_root / "doc" / "sample_sorry_list.json"
    sample_sorries = load_sorry_json(json_path=sample_sorries_path)
    return SQLSorry.from_json_sorry(sample_sorries[0])


def _create_agent(client: TestClient, auth_headers: dict) -> str:
    response = client.post("/agents/", json={"name": "test agent"}, headers=auth_headers)
    assert response.status_code == 201
    agent = response.json()
    return agent["id"]


def _add_test_sorry(session: Session):
    test_sorry = _select_sample_sorry()
    session.add(test_sorry)
    session.commit()


def _add_test_sorries(session: Session, n: int):
    sorries = (
        SQLSorry.from_json_sorry(
            sorry_with_defaults(
                goal=f"test goal {i}", repo_remote=f"https://example.com/repo{i}"
            )
        )
        for i in range(n)
    )
    session.add_all(sorries)
    session.commit()


def test_create_challenge(session, client, auth_headers):
    _add_test_sorry(session)
    agent_id = _create_agent(client, auth_headers)

    new_challenge_response = client.post(f"/agents/{agent_id}/challenges", headers=auth_headers)
    assert new_challenge_response.status_code == 201
    assert "id" in new_challenge_response.json()


def test_create_challenge_unauthenticated(session, client, auth_headers):
    _add_test_sorry(session)
    agent_id = _create_agent(client, auth_headers)

    response = client.post(f"/agents/{agent_id}/challenges")
    assert response.status_code == 401


def test_submit_challenge(session: Session, client: TestClient, auth_headers: dict):
    _add_test_sorry(session)
    agent_id = _create_agent(client, auth_headers)

    new_challenge_response = client.post(f"/agents/{agent_id}/challenges", headers=auth_headers)
    assert new_challenge_response.status_code == 201
    challenge_id = new_challenge_response.json()["id"]

    proof_text = "this is my proof"
    submit_challenge_response = client.post(
        f"/agents/{agent_id}/challenges/{challenge_id}/submit/",
        json={"proof": proof_text},
        headers=auth_headers,
    )

    assert submit_challenge_response.status_code == 200
    submitted_challenge = submit_challenge_response.json()
    assert submitted_challenge["status"] == ChallengeStatus.PENDING_VERIFICATION.value
    assert submitted_challenge["submission"] == proof_text

    db = SQLDatabase(session)
    challenge = db.get_challenge(challenge_id)
    assert challenge is not None
    assert challenge.status == ChallengeStatus.PENDING_VERIFICATION
    assert challenge.submission == proof_text


def test_submit_challenge_unauthenticated(session: Session, client: TestClient, auth_headers: dict):
    _add_test_sorry(session)
    agent_id = _create_agent(client, auth_headers)

    new_challenge_response = client.post(f"/agents/{agent_id}/challenges", headers=auth_headers)
    assert new_challenge_response.status_code == 201
    challenge_id = new_challenge_response.json()["id"]

    response = client.post(
        f"/agents/{agent_id}/challenges/{challenge_id}/submit/",
        json={"proof": "some proof"},
    )
    assert response.status_code == 401


def test_cannot_submit_to_other_user_challenge(session: Session, client: TestClient):
    _add_test_sorry(session)
    
    user1_response = client.post(
        "/auth/register",
        json={"email": "user1@example.com", "password": "pass123"},
    )
    assert user1_response.status_code == 201
    
    user2_response = client.post(
        "/auth/register",
        json={"email": "user2@example.com", "password": "pass123"},
    )
    assert user2_response.status_code == 201

    token1 = client.post(
        "/auth/token",
        data={"username": "user1@example.com", "password": "pass123"},
    ).json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token1}"}

    token2 = client.post(
        "/auth/token",
        data={"username": "user2@example.com", "password": "pass123"},
    ).json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    agent_id = _create_agent(client, headers1)
    challenge_response = client.post(f"/agents/{agent_id}/challenges", headers=headers1)
    challenge_id = challenge_response.json()["id"]

    response = client.post(
        f"/agents/{agent_id}/challenges/{challenge_id}/submit/",
        json={"proof": "malicious proof"},
        headers=headers2,
    )
    assert response.status_code == 403


def test_cannot_request_challenge_for_other_user_agent(session: Session, client: TestClient):
    _add_test_sorry(session)
    
    user1_response = client.post(
        "/auth/register",
        json={"email": "user1@example.com", "password": "pass123"},
    )
    assert user1_response.status_code == 201
    
    user2_response = client.post(
        "/auth/register",
        json={"email": "user2@example.com", "password": "pass123"},
    )
    assert user2_response.status_code == 201

    token1 = client.post(
        "/auth/token",
        data={"username": "user1@example.com", "password": "pass123"},
    ).json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token1}"}

    token2 = client.post(
        "/auth/token",
        data={"username": "user2@example.com", "password": "pass123"},
    ).json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    agent_id = _create_agent(client, headers1)

    response = client.post(f"/agents/{agent_id}/challenges", headers=headers2)
    assert response.status_code == 403


def test_cannot_view_other_user_challenges(session: Session, client: TestClient):
    _add_test_sorry(session)
    
    user1_response = client.post(
        "/auth/register",
        json={"email": "user1@example.com", "password": "pass123"},
    )
    assert user1_response.status_code == 201
    
    user2_response = client.post(
        "/auth/register",
        json={"email": "user2@example.com", "password": "pass123"},
    )
    assert user2_response.status_code == 201

    token1 = client.post(
        "/auth/token",
        data={"username": "user1@example.com", "password": "pass123"},
    ).json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token1}"}

    token2 = client.post(
        "/auth/token",
        data={"username": "user2@example.com", "password": "pass123"},
    ).json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    agent_id = _create_agent(client, headers1)
    client.post(f"/agents/{agent_id}/challenges", headers=headers1)

    response = client.get(f"/agents/{agent_id}/challenges/", headers=headers2)
    assert response.status_code == 403


def test_get_agent_challenges_paginated(session, client, auth_headers):
    _add_test_sorries(session, n=10)
    agent_id = _create_agent(client, auth_headers)

    challenge_ids = []
    for _ in range(5):
        response = client.post(f"/agents/{agent_id}/challenges", headers=auth_headers)
        assert response.status_code == 201
        challenge_ids.append(response.json()["id"])

    response = client.get(f"/agents/{agent_id}/challenges/?skip=0&limit=2", headers=auth_headers)
    assert response.status_code == 200
    challenges = response.json()
    assert len(challenges) == 2
    assert challenges[0]["id"] == challenge_ids[0]
    assert challenges[1]["id"] == challenge_ids[1]

    response = client.get(f"/agents/{agent_id}/challenges/?skip=2&limit=2", headers=auth_headers)
    assert response.status_code == 200
    challenges = response.json()
    assert len(challenges) == 2
    assert challenges[0]["id"] == challenge_ids[2]
    assert challenges[1]["id"] == challenge_ids[3]

    response = client.get(f"/agents/{agent_id}/challenges/?skip=4&limit=2", headers=auth_headers)
    assert response.status_code == 200
    challenges = response.json()
    assert len(challenges) == 1
    assert challenges[0]["id"] == challenge_ids[4]

    response = client.get(f"/agents/{agent_id}/challenges/?skip=5&limit=2", headers=auth_headers)
    assert response.status_code == 200
    challenges = response.json()
    assert len(challenges) == 0

    response = client.get(f"/agents/{agent_id}/challenges/", headers=auth_headers)
    assert response.status_code == 200
    challenges = response.json()
    assert len(challenges) == 5


def test_get_challenges_for_non_existent_agent(client, auth_headers):
    non_existent_agent_id = "non_existent_agent"
    response = client.get(
        f"/agents/{non_existent_agent_id}/challenges/?skip=0&limit=2",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_agent_gets_unique_sorries_until_exhausted(session, client, auth_headers):
    _add_test_sorries(session, n=100)
    agent_id = _create_agent(client, auth_headers)

    requested_sorry_ids = set()
    for i in range(100):
        response = client.post(f"/agents/{agent_id}/challenges/", headers=auth_headers)
        assert response.status_code == 201, f"Failed on request {i + 1}"
        challenge_data = response.json()
        sorry_id = challenge_data["sorry"]["id"]
        assert sorry_id not in requested_sorry_ids
        requested_sorry_ids.add(sorry_id)

    assert len(requested_sorry_ids) == 100

    response = client.post(f"/agents/{agent_id}/challenges/", headers=auth_headers)
    assert response.status_code == 422
    assert "No sorry to serve" in response.text


def test_request_challenge_when_no_sorries_exist(client, auth_headers):
    agent_id = _create_agent(client, auth_headers)

    response = client.post(f"/agents/{agent_id}/challenges/", headers=auth_headers)
    assert response.status_code == 422
    assert "No sorry to serve" in response.text


def test_challenge_agent_relationship(session: Session, client: TestClient, auth_headers: dict):
    _add_test_sorry(session)
    agent_id = _create_agent(client, auth_headers)

    response = client.post(f"/agents/{agent_id}/challenges", headers=auth_headers)
    assert response.status_code == 201
    challenge_id = response.json()["id"]

    db = SQLDatabase(session)
    challenge = db.get_challenge(challenge_id)
    assert challenge is not None
    assert challenge.agent is not None
    assert challenge.agent.id == agent_id


def test_agent_challenges_relationship(session: Session, client: TestClient, auth_headers: dict):
    _add_test_sorry(session)
    agent_id = _create_agent(client, auth_headers)
    _add_test_sorries(session, n=3)

    challenge_ids = set()
    for _ in range(3):
        response = client.post(f"/agents/{agent_id}/challenges", headers=auth_headers)
        assert response.status_code == 201
        challenge_ids.add(response.json()["id"])

    db = SQLDatabase(session)
    agent = db.get_agent(agent_id)
    assert agent is not None
    assert len(agent.challenges) == 3

    fetched_challenge_ids = {c.id for c in agent.challenges}
    assert fetched_challenge_ids == challenge_ids
