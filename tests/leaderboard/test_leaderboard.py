def test_leaderboard_returns_public_agents_only(client, auth_headers):
    # Create two agents - one visible, one hidden
    visible_agent = client.post(
        "/agents/",
        json={"name": "visible agent", "visible": True, "description": "A visible agent"},
        headers=auth_headers,
    )
    assert visible_agent.status_code == 201

    hidden_agent = client.post(
        "/agents/",
        json={"name": "hidden agent", "visible": False, "description": "A hidden agent"},
        headers=auth_headers,
    )
    assert hidden_agent.status_code == 201

    # Get leaderboard
    response = client.get("/leaderboard")
    assert response.status_code == 200
    leaderboard = response.json()

    # Only visible agent should appear
    agent_names = [entry["agent_name"] for entry in leaderboard]
    assert "visible agent" in agent_names
    assert "hidden agent" not in agent_names


def test_leaderboard_includes_description(client, auth_headers):
    # Create agent with description
    agent_response = client.post(
        "/agents/",
        json={
            "name": "test agent",
            "description": "This is a test agent description",
            "visible": True,
        },
        headers=auth_headers,
    )
    assert agent_response.status_code == 201

    # Get leaderboard
    response = client.get("/leaderboard")
    assert response.status_code == 200
    leaderboard = response.json()

    # Find our agent
    agent_entry = next((e for e in leaderboard if e["agent_name"] == "test agent"), None)
    assert agent_entry is not None
    assert agent_entry["description"] == "This is a test agent description"


def test_leaderboard_no_auth_required(client):
    # Leaderboard should be publicly accessible
    response = client.get("/leaderboard")
    assert response.status_code == 200


def test_leaderboard_agent_visibility_update(client, auth_headers):
    # Create visible agent
    agent_response = client.post(
        "/agents/",
        json={"name": "test agent", "visible": True},
        headers=auth_headers,
    )
    agent_id = agent_response.json()["id"]

    # Verify it appears on leaderboard
    response = client.get("/leaderboard")
    agent_names = [e["agent_name"] for e in response.json()]
    assert "test agent" in agent_names

    # Hide the agent
    client.patch(
        f"/agents/{agent_id}",
        json={"visible": False},
        headers=auth_headers,
    )

    # Verify it's now hidden from leaderboard
    response = client.get("/leaderboard")
    agent_names = [e["agent_name"] for e in response.json()]
    assert "test agent" not in agent_names


def test_leaderboard_description_can_be_null(client, auth_headers):
    # Create agent without description
    agent_response = client.post(
        "/agents/",
        json={"name": "agent without description"},
        headers=auth_headers,
    )
    assert agent_response.status_code == 201

    # Get leaderboard
    response = client.get("/leaderboard")
    assert response.status_code == 200
    leaderboard = response.json()

    # Find our agent
    agent_entry = next((e for e in leaderboard if e["agent_name"] == "agent without description"), None)
    assert agent_entry is not None
    assert agent_entry["description"] is None
