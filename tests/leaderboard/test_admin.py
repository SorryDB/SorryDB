from fastapi.testclient import TestClient
from sqlmodel import Session

from sorrydb.leaderboard.model.sorry import SQLSorry
from tests.mock_sorries import sorry_with_defaults


def test_admin_can_access_admin_ui(client: TestClient, admin_auth_headers: dict):
    response = client.get("/admin/", headers=admin_auth_headers)
    assert response.status_code == 200


def test_non_admin_denied_admin_access(client: TestClient, auth_headers: dict):
    response = client.get("/admin/", headers=auth_headers)
    assert response.status_code == 403


def test_unauthenticated_denied_admin_access(client: TestClient):
    response = client.get("/admin/")
    assert response.status_code == 401


def test_admin_can_view_all_models(client: TestClient, admin_auth_headers: dict):
    response = client.get("/admin/user/list", headers=admin_auth_headers)
    assert response.status_code == 200

    response = client.get("/admin/agent/list", headers=admin_auth_headers)
    assert response.status_code == 200

    response = client.get("/admin/challenge/list", headers=admin_auth_headers)
    assert response.status_code == 200

    response = client.get("/admin/sql-sorry/list", headers=admin_auth_headers)
    assert response.status_code == 200


def test_regular_api_unaffected_by_admin(
    client: TestClient, session: Session, auth_headers: dict
):
    sorry = SQLSorry.from_json_sorry(
        sorry_with_defaults(goal="api test", repo_remote="https://example.com/repo")
    )
    session.add(sorry)
    session.commit()
    
    agent_response = client.post(
        "/agents/", json={"name": "api agent"}, headers=auth_headers
    )
    assert agent_response.status_code == 201
    
    challenge_response = client.post(
        f"/agents/{agent_response.json()['id']}/challenges", headers=auth_headers
    )
    assert challenge_response.status_code == 201
    
    agents_response = client.get("/agents/", headers=auth_headers)
    assert agents_response.status_code == 200
