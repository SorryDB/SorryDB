def test_create_agent(client, auth_headers):
    response = client.post("/agents/", json={"name": "test agent"}, headers=auth_headers)
    assert response.status_code == 201

    response = client.get("/agents/", headers=auth_headers)
    assert response.status_code == 200
    response_json = response.json()
    assert any(agent["name"] == "test agent" for agent in response_json)


def test_create_agent_unauthenticated(client):
    response = client.post("/agents/", json={"name": "test agent"})
    assert response.status_code == 401


def test_get_agents_paginated(client, auth_headers):
    agent_ids = []
    agent_names = []
    for i in range(5):
        name = f"test agent {i}"
        response = client.post("/agents/", json={"name": name}, headers=auth_headers)
        assert response.status_code == 201
        agent_ids.append(response.json()["id"])
        agent_names.append(name)

    response = client.get("/agents/?skip=0&limit=2", headers=auth_headers)
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) == 2
    assert agents[0]["id"] == agent_ids[0]
    assert agents[0]["name"] == agent_names[0]
    assert agents[1]["id"] == agent_ids[1]
    assert agents[1]["name"] == agent_names[1]

    response = client.get("/agents/?skip=2&limit=2", headers=auth_headers)
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) == 2
    assert agents[0]["id"] == agent_ids[2]
    assert agents[0]["name"] == agent_names[2]
    assert agents[1]["id"] == agent_ids[3]
    assert agents[1]["name"] == agent_names[3]

    response = client.get("/agents/?skip=4&limit=2", headers=auth_headers)
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) == 1
    assert agents[0]["id"] == agent_ids[4]
    assert agents[0]["name"] == agent_names[4]

    response = client.get("/agents/?skip=5&limit=2", headers=auth_headers)
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) == 0

    response = client.get("/agents/?skip=0&limit=10", headers=auth_headers)
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) == 5
    assert agents[0]["id"] == agent_ids[0]
    assert agents[4]["id"] == agent_ids[4]

    response = client.get("/agents/", headers=auth_headers)
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) == 5


def test_user_only_sees_own_agents(client):
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

    token1_response = client.post(
        "/auth/token",
        data={"username": "user1@example.com", "password": "pass123"},
    )
    token1 = token1_response.json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token1}"}

    token2_response = client.post(
        "/auth/token",
        data={"username": "user2@example.com", "password": "pass123"},
    )
    token2 = token2_response.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    client.post("/agents/", json={"name": "user1 agent"}, headers=headers1)
    client.post("/agents/", json={"name": "user2 agent"}, headers=headers2)

    user1_agents = client.get("/agents/", headers=headers1).json()
    assert len(user1_agents) == 1
    assert user1_agents[0]["name"] == "user1 agent"

    user2_agents = client.get("/agents/", headers=headers2).json()
    assert len(user2_agents) == 1
    assert user2_agents[0]["name"] == "user2 agent"


def test_cannot_access_other_user_agent_by_id(client):
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

    agent_response = client.post("/agents/", json={"name": "user1 agent"}, headers=headers1)
    user1_agent_id = agent_response.json()["id"]

    response = client.get(f"/agents/{user1_agent_id}", headers=headers2)
    assert response.status_code in [403, 404]
