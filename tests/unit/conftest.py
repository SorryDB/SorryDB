"""Fixtures for unit tests."""

import pytest


@pytest.fixture
def leaderboard_env(monkeypatch):
    """Set up leaderboard environment variables for testing.

    Sets LEADERBOARD_USERNAME and LEADERBOARD_PASSWORD to standard test values.
    Use this fixture in tests that need valid credentials without specifying them manually.
    """
    monkeypatch.setenv("LEADERBOARD_USERNAME", "test@example.com")
    monkeypatch.setenv("LEADERBOARD_PASSWORD", "testpass123")


@pytest.fixture
def mock_sorrydb_api_client(monkeypatch):
    """
    Mock the entire sorrydb_api_client module for unit testing.

    This fixture provides complete mocking of the API client including:
    - Authentication (AuthApi.login_auth_token_post)
    - Agent operations (list_agents_agents_get, register_agent_agents_post)
    - Challenge operations (request_sorry_challenge, submit_proof)

    Returns:
        dict: Dictionary containing all mocked objects for assertions:
            - 'client': The main mock client module
            - 'auth_api': Mocked AuthApi instance
            - 'default_api': Mocked DefaultApi instance
            - 'configuration': Mocked Configuration instance
            - 'api_context': Mocked ApiClient context manager
    """
    from unittest.mock import Mock, MagicMock, patch

    with patch("sorrydb.runners.leaderboard_runner.sorrydb_api_client") as mock_client:
        # Mock Configuration
        mock_config = Mock()
        mock_config.access_token = None
        mock_client.Configuration.return_value = mock_config

        # Mock authentication response
        mock_token_response = Mock()
        mock_token_response.access_token = "test_access_token_123"

        # Mock AuthApi
        mock_auth_api = Mock()
        mock_auth_api.login_auth_token_post.return_value = mock_token_response

        # Mock agent response
        mock_agent = Mock()
        mock_agent.id = "test_agent_id_456"
        mock_agent.name = "test_agent"

        # Mock DefaultApi
        mock_default_api = Mock()
        # Reset mock to ensure clean state for each test
        mock_default_api.reset_mock()
        mock_default_api.list_agents_agents_get.return_value = []
        mock_default_api.register_agent_agents_post.return_value = mock_agent

        # Mock challenge response with SQL Sorry data (complete structure for from_sql_sorry)
        from datetime import datetime

        mock_sorry = Mock()
        mock_sorry.id = "sorry_789"
        # All attributes required by Sorry.from_sql_sorry()
        mock_sorry.remote = "https://github.com/test/repo.git"
        mock_sorry.branch = "main"
        mock_sorry.commit = "abc123def456"
        mock_sorry.lean_version = "v4.0.0"
        mock_sorry.path = "Test/File.lean"
        mock_sorry.start_line = 42
        mock_sorry.start_column = 0
        mock_sorry.end_line = 42
        mock_sorry.end_column = 10
        mock_sorry.goal = "⊢ True"
        mock_sorry.url = "https://github.com/test/repo/blob/abc123def456/Test/File.lean#L42"
        mock_sorry.blame_email_hash = "test_email_hash"
        mock_sorry.blame_date = datetime(2024, 1, 1)
        mock_sorry.inclusion_date = datetime(2024, 1, 1)

        mock_challenge = Mock()
        mock_challenge.id = "challenge_123"
        mock_challenge.sorry = mock_sorry

        mock_default_api.request_sorry_challenge_agents_agent_id_challenges_post.return_value = (
            mock_challenge
        )

        # Mock submission response
        mock_submission_response = Mock()
        mock_submission_response.success = True
        mock_default_api.submit_proof_agents_agent_id_challenges_challenge_id_submit_post.return_value = (
            mock_submission_response
        )

        # Setup ApiClient context manager
        mock_api_context = MagicMock()
        mock_api_context.__enter__.return_value = mock_api_context
        mock_api_context.__exit__.return_value = None
        mock_client.ApiClient.return_value = mock_api_context

        # Wire up the APIs to the context
        mock_client.AuthApi.return_value = mock_auth_api
        mock_client.DefaultApi.return_value = mock_default_api

        # Mock data models
        mock_client.AgentCreate = Mock
        mock_client.ChallengeSubmissionCreate = Mock

        yield {
            "client": mock_client,
            "auth_api": mock_auth_api,
            "default_api": mock_default_api,
            "configuration": mock_config,
            "api_context": mock_api_context,
            "agent": mock_agent,
            "challenge": mock_challenge,
            "sorry": mock_sorry,
        }


@pytest.fixture
def mock_git_operations():
    """
    Mock git operations (Repo.clone_from, checkout) for testing.

    Returns:
        dict: Dictionary with 'repo' mock object
    """
    from unittest.mock import Mock, patch

    with patch("sorrydb.runners.leaderboard_runner.Repo") as mock_repo_class:
        mock_repo_instance = Mock()
        mock_repo_instance.git.checkout.return_value = None
        mock_repo_class.clone_from.return_value = mock_repo_instance
        mock_repo_class.return_value = mock_repo_instance

        yield {"repo_class": mock_repo_class, "repo": mock_repo_instance}


@pytest.fixture
def mock_verify_proof():
    """
    Mock the verify_proof function for testing.

    Returns:
        Mock: The mocked verify_proof function (defaults to returning True)
    """
    from unittest.mock import patch

    with patch("sorrydb.runners.leaderboard_runner.verify_proof") as mock_verify:
        mock_verify.return_value = True
        yield mock_verify
