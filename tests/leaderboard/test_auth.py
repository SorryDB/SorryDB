import time

from fastapi.testclient import TestClient


def test_register_user(client: TestClient):
    response = client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "securepass123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "user@example.com"
    assert "id" in data
    assert "hashed_password" not in data


def test_register_duplicate_email(client: TestClient):
    client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "password123"},
    )
    response = client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "different123"},
    )
    assert response.status_code == 409


def test_login_success(client: TestClient):
    client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "testpass123"},
    )
    response = client.post(
        "/auth/token",
        data={"username": "user@example.com", "password": "testpass123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client: TestClient):
    client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "correctpass"},
    )
    response = client.post(
        "/auth/token",
        data={"username": "user@example.com", "password": "wrongpass"},
    )
    assert response.status_code == 401


def test_login_nonexistent_user(client: TestClient):
    response = client.post(
        "/auth/token",
        data={"username": "nobody@example.com", "password": "anypass"},
    )
    assert response.status_code == 401


def test_get_current_user(client: TestClient, auth_headers: dict):
    response = client.get("/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "hashed_password" not in data


def test_get_current_user_no_token(client: TestClient):
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_get_current_user_invalid_token(client: TestClient):
    response = client.get(
        "/auth/me", headers={"Authorization": "Bearer invalidtoken"}
    )
    assert response.status_code == 401


def test_full_auth_flow(client: TestClient):
    register_response = client.post(
        "/auth/register",
        json={"email": "flow@example.com", "password": "flowpass123"},
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/auth/token",
        data={"username": "flow@example.com", "password": "flowpass123"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    agent_response = client.post("/agents/", json={"name": "flow agent"}, headers=headers)
    assert agent_response.status_code == 201
    assert agent_response.json()["name"] == "flow agent"


def test_admin_access(client: TestClient, admin_auth_headers: dict):
    response = client.get("/auth/me", headers=admin_auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["is_admin"] is True


def test_malformed_token_missing_bearer(client: TestClient):
    response = client.get("/auth/me", headers={"Authorization": "invalidtoken"})
    assert response.status_code == 401


def test_malformed_token_no_authorization_header(client: TestClient):
    response = client.get("/auth/me", headers={})
    assert response.status_code == 401
