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


def test_get_agents_paginated():
    # Create 5 agents
    agent_ids = []
    agent_names = []
    for i in range(5):
        name = f"test agent {i}"
        response = client.post("/agents/", json={"name": name})
        assert response.status_code == 201
        agent_ids.append(response.json()["id"])
        agent_names.append(name)

    # Get first 2 agents
    response = client.get("/agents/?skip=0&limit=2")
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) == 2
    assert agents[0]["id"] == agent_ids[0]
    assert agents[0]["name"] == agent_names[0]
    assert agents[1]["id"] == agent_ids[1]
    assert agents[1]["name"] == agent_names[1]

    # Get next 2 agents
    response = client.get("/agents/?skip=2&limit=2")
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) == 2
    assert agents[0]["id"] == agent_ids[2]
    assert agents[0]["name"] == agent_names[2]
    assert agents[1]["id"] == agent_ids[3]
    assert agents[1]["name"] == agent_names[3]

    # Get last agent
    response = client.get("/agents/?skip=4&limit=2")
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) == 1
    assert agents[0]["id"] == agent_ids[4]
    assert agents[0]["name"] == agent_names[4]

    # Skip beyond available agents
    response = client.get("/agents/?skip=5&limit=2")
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) == 0

    # Limit larger than available agents
    response = client.get("/agents/?skip=0&limit=10")
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) == 5
    assert agents[0]["id"] == agent_ids[0]
    assert agents[4]["id"] == agent_ids[4]

    # Default pagination (skip=0, limit=10 by default in API)
    response = client.get("/agents/")
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) == 5  # Assuming default limit is >= 5
