"""Unit tests for LeaderboardRunner using mocked API client."""

from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from sorrydb.runners.leaderboard_runner import LeaderboardRunner
from sorrydb.runners.rfl_strategy import RflStrategy


class TestLeaderboardRunnerInitialization:
    """Test LeaderboardRunner initialization, authentication, and agent registration."""

    def test_successful_initialization_new_agent(
        self, mock_sorrydb_api_client, leaderboard_env, tmp_path
    ):
        """Test successful initialization with authentication and new agent registration."""
        # Create runner
        strategy = Mock()
        runner = LeaderboardRunner("test_agent", strategy, tmp_path)

        # Verify authentication was called
        mock_sorrydb_api_client["auth_api"].login_auth_token_post.assert_called_once_with(
            username="test@example.com", password="testpass123"
        )

        # Verify access token was set
        assert (
            mock_sorrydb_api_client["configuration"].access_token
            == "test_access_token_123"
        )

        # Verify agent registration
        mock_sorrydb_api_client["default_api"].list_agents_agents_get.assert_called_once()
        mock_sorrydb_api_client[
            "default_api"
        ].register_agent_agents_post.assert_called_once()

        # Verify runner state
        assert runner.agent_id == "test_agent_id_456"
        assert runner.name == "test_agent"
        assert runner.strategy == strategy
        assert runner.lean_data_path == tmp_path

    def test_successful_initialization_existing_agent(
        self, mock_sorrydb_api_client, leaderboard_env, tmp_path
    ):
        """Test initialization when agent already exists (skips registration)."""
        # Mock existing agent - must set attributes explicitly (name is special in Mock)
        existing_agent = Mock()
        existing_agent.id = "existing_agent_id"
        existing_agent.name = "test_agent"

        mock_sorrydb_api_client["default_api"].list_agents_agents_get.return_value = [
            existing_agent
        ]

        # Create runner
        strategy = Mock()
        runner = LeaderboardRunner("test_agent", strategy, tmp_path)

        # Verify agent registration was NOT called (agent already exists)
        mock_sorrydb_api_client[
            "default_api"
        ].register_agent_agents_post.assert_not_called()

        # Verify runner uses existing agent ID
        assert runner.agent_id == "existing_agent_id"

    def test_initialization_missing_credentials(self, mock_sorrydb_api_client, tmp_path):
        """Test initialization fails when credentials are missing."""
        # Don't set environment variables

        with pytest.raises(ValueError, match="LEADERBOARD_USERNAME and LEADERBOARD_PASSWORD"):
            LeaderboardRunner("test_agent", Mock(), tmp_path)

    def test_initialization_authentication_failure(
        self, mock_sorrydb_api_client, monkeypatch, tmp_path
    ):
        """Test initialization fails when authentication fails."""
        # Setup environment
        monkeypatch.setenv("LEADERBOARD_USERNAME", "test@example.com")
        monkeypatch.setenv("LEADERBOARD_PASSWORD", "wrongpassword")

        # Mock authentication failure
        mock_sorrydb_api_client["auth_api"].login_auth_token_post.side_effect = Exception(
            "Invalid credentials"
        )

        with pytest.raises(ValueError, match="Failed to authenticate with leaderboard API"):
            LeaderboardRunner("test_agent", Mock(), tmp_path)

    def test_initialization_multiple_agents_with_same_name(
        self, mock_sorrydb_api_client, leaderboard_env, tmp_path, caplog
    ):
        """Test initialization when multiple agents have the same name.

        Note: The current implementation catches and logs the ValueError but doesn't re-raise it.
        This leaves the runner with agent_id = None. This test documents this behavior.
        """
        # Mock multiple agents with same name - must set attributes explicitly
        agent1 = Mock()
        agent1.id = "agent1"
        agent1.name = "test_agent"

        agent2 = Mock()
        agent2.id = "agent2"
        agent2.name = "test_agent"

        mock_sorrydb_api_client["default_api"].list_agents_agents_get.return_value = [
            agent1,
            agent2,
        ]

        # LeaderboardRunner is created but with agent_id = None (exception is caught and logged)
        runner = LeaderboardRunner("test_agent", Mock(), tmp_path)

        # Verify agent_id is None (registration failed)
        assert runner.agent_id is None

        # Verify error was logged
        assert "More than one agent with name" in caplog.text

    def test_initialization_custom_host(
        self, mock_sorrydb_api_client, leaderboard_env, monkeypatch, tmp_path
    ):
        """Test initialization with custom LEADERBOARD_HOST."""
        # Setup custom host (credentials already set by leaderboard_env)
        monkeypatch.setenv("LEADERBOARD_HOST", "http://custom-host:9000")

        # Create runner
        runner = LeaderboardRunner("test_agent", Mock(), tmp_path)

        # Verify Configuration was created with custom host
        mock_sorrydb_api_client["client"].Configuration.assert_called_with(
            host="http://custom-host:9000"
        )


class TestLeaderboardRunnerChallengeAttempt:
    """Test LeaderboardRunner challenge attempt workflow."""

    def test_successful_challenge_attempt(
        self,
        mock_sorrydb_api_client,
        mock_git_operations,
        mock_verify_proof,
        leaderboard_env,
        tmp_path,
    ):
        """Test successful challenge request, proof generation, and submission."""
        # Mock strategy
        mock_strategy = Mock()
        mock_strategy.prove_sorry.return_value = "by rfl"

        # Create runner and attempt challenge
        runner = LeaderboardRunner("test_agent", mock_strategy, tmp_path)
        runner.attempt_challenge()

        # Verify challenge was requested
        mock_sorrydb_api_client[
            "default_api"
        ].request_sorry_challenge_agents_agent_id_challenges_post.assert_called_once_with(
            "test_agent_id_456"
        )

        # Verify git operations
        mock_git_operations["repo_class"].clone_from.assert_called_once_with(
            "https://github.com/test/repo.git",
            tmp_path / "repo" / "v4.0.0" / "abc123def456",
        )
        mock_git_operations["repo"].git.checkout.assert_called_once_with("abc123def456")

        # Verify strategy was called
        mock_strategy.prove_sorry.assert_called_once()

        # Verify proof verification was called
        mock_verify_proof.assert_called_once()

        # Verify proof was submitted
        mock_sorrydb_api_client[
            "default_api"
        ].submit_proof_agents_agent_id_challenges_challenge_id_submit_post.assert_called_once()

    def test_challenge_attempt_with_existing_repo(
        self,
        mock_sorrydb_api_client,
        mock_git_operations,
        mock_verify_proof,
        leaderboard_env,
        tmp_path,
    ):
        """Test challenge attempt when repository already exists locally."""
        # Create the repo directory to simulate existing checkout
        repo_path = tmp_path / "repo" / "v4.0.0" / "abc123def456"
        repo_path.mkdir(parents=True)

        # Mock strategy
        mock_strategy = Mock()
        mock_strategy.prove_sorry.return_value = "by rfl"

        # Create runner and attempt challenge
        runner = LeaderboardRunner("test_agent", mock_strategy, tmp_path)
        runner.attempt_challenge()

        # Verify clone was NOT called (repo already exists)
        mock_git_operations["repo_class"].clone_from.assert_not_called()

        # Verify Repo was instantiated with existing path
        mock_git_operations["repo_class"].assert_called_once_with(repo_path)

    def test_challenge_attempt_proof_verification_fails(
        self,
        mock_sorrydb_api_client,
        mock_git_operations,
        mock_verify_proof,
        leaderboard_env,
        tmp_path,
    ):
        """Test challenge attempt when proof verification fails (proof not submitted)."""
        # Mock strategy and verification failure
        mock_strategy = Mock()
        mock_strategy.prove_sorry.return_value = "invalid proof"
        mock_verify_proof.return_value = False

        # Create runner and attempt challenge
        runner = LeaderboardRunner("test_agent", mock_strategy, tmp_path)
        runner.attempt_challenge()

        # Verify proof was NOT submitted (verification failed)
        mock_sorrydb_api_client[
            "default_api"
        ].submit_proof_agents_agent_id_challenges_challenge_id_submit_post.assert_not_called()

    def test_challenge_attempt_no_proof_generated(
        self,
        mock_sorrydb_api_client,
        mock_git_operations,
        mock_verify_proof,
        leaderboard_env,
        tmp_path,
    ):
        """Test challenge attempt when strategy returns no proof."""
        # Mock strategy returning None
        mock_strategy = Mock()
        mock_strategy.prove_sorry.return_value = None

        # Create runner and attempt challenge
        runner = LeaderboardRunner("test_agent", mock_strategy, tmp_path)
        runner.attempt_challenge()

        # Verify verification was NOT called (no proof to verify)
        mock_verify_proof.assert_not_called()

        # Verify proof was NOT submitted
        mock_sorrydb_api_client[
            "default_api"
        ].submit_proof_agents_agent_id_challenges_challenge_id_submit_post.assert_not_called()


class TestLeaderboardRunnerErrorHandling:
    """Test error handling in LeaderboardRunner."""

    def test_challenge_request_api_error(
        self,
        mock_sorrydb_api_client,
        mock_git_operations,
        leaderboard_env,
        tmp_path,
    ):
        """Test handling of API errors during challenge request."""
        # Mock API error
        mock_sorrydb_api_client[
            "default_api"
        ].request_sorry_challenge_agents_agent_id_challenges_post.side_effect = Exception(
            "API Error"
        )

        # Create runner
        runner = LeaderboardRunner("test_agent", Mock(), tmp_path)

        # Verify error is raised
        with pytest.raises(Exception, match="API Error"):
            runner.attempt_challenge()

    def test_git_clone_failure(
        self,
        mock_sorrydb_api_client,
        mock_git_operations,
        mock_verify_proof,
        leaderboard_env,
        tmp_path,
    ):
        """Test handling of git clone failures."""
        # Mock git clone failure
        mock_git_operations["repo_class"].clone_from.side_effect = Exception(
            "Git clone failed"
        )

        mock_strategy = Mock()
        mock_strategy.prove_sorry.return_value = "by rfl"

        # Create runner
        runner = LeaderboardRunner("test_agent", mock_strategy, tmp_path)

        # Verify error is raised
        with pytest.raises(Exception, match="Git clone failed"):
            runner.attempt_challenge()

    def test_strategy_raises_exception(
        self,
        mock_sorrydb_api_client,
        mock_git_operations,
        mock_verify_proof,
        leaderboard_env,
        tmp_path,
    ):
        """Test handling when strategy raises an exception."""
        # Mock strategy exception
        mock_strategy = Mock()
        mock_strategy.prove_sorry.side_effect = Exception("Strategy failed")

        # Create runner
        runner = LeaderboardRunner("test_agent", mock_strategy, tmp_path)

        # Verify error is raised
        with pytest.raises(Exception, match="Strategy failed"):
            runner.attempt_challenge()

        # Verify submission was not attempted
        mock_sorrydb_api_client[
            "default_api"
        ].submit_proof_agents_agent_id_challenges_challenge_id_submit_post.assert_not_called()

