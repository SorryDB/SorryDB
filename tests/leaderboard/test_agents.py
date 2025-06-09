from fastapi.testclient import TestClient

from sorrydb.leaderboard.api.app import app

client = TestClient(app)


def test_create_agent():
    response = client.post("/agents/", json={"name": "test agent"})
    assert response.status_code == 201

    response = client.get("/agents/")
    assert response.status_code == 200
    response_json = response.json()
    assert any(agent["name"] == "test agent" for agent in response_json)
