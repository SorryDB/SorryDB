import logging
import os
from pathlib import Path

import sorrydb_api_client
from git import Repo

from sorrydb.runners.json_runner import SorryStrategy
from sorrydb.runners.runner_utils import ensure_repo_is_prepared
from sorrydb.database.sorry import Sorry
from sorrydb.utils.verify import verify_proof

logger = logging.getLogger(__name__)


class LeaderboardRunner:
    """
    Runner for participating in the SorryDB leaderboard competition.

    The LeaderboardRunner connects to the leaderboard API, registers an agent,
    requests challenges (sorry statements to prove), attempts to solve them using
    a provided strategy, and submits verified proofs back to the leaderboard.

    Environment Variables:
        LEADERBOARD_USERNAME: Email for API authentication
        LEADERBOARD_PASSWORD: Password for API authentication
        LEADERBOARD_HOST: API host URL (default: http://127.0.0.1:8080)
    """

    def __init__(
        self,
        name: str,
        strategy: SorryStrategy,
        lean_data_path: Path | None = None,
    ):
        self.name = name
        self.strategy = strategy
        self.lean_data_path = lean_data_path

        self.agent_id = None

        # Authenticate and configure API client
        self.api_configuration = self._authenticate()

        self._register_agent()

    def _authenticate(self) -> sorrydb_api_client.Configuration:
        """Authenticate with the leaderboard API and return configured client.

        Raises:
            ValueError: If credentials are missing or authentication fails
        """
        # Get credentials from environment variables
        username = os.getenv("LEADERBOARD_USERNAME")
        password = os.getenv("LEADERBOARD_PASSWORD")
        host = os.getenv("LEADERBOARD_HOST", "http://127.0.0.1:8080")

        if not username or not password:
            raise ValueError(
                "LEADERBOARD_USERNAME and LEADERBOARD_PASSWORD environment variables must be set"
            )

        # Create initial configuration
        configuration = sorrydb_api_client.Configuration(host=host)

        # Authenticate to get access token
        try:
            with sorrydb_api_client.ApiClient(configuration) as api_client:
                auth_api = sorrydb_api_client.AuthApi(api_client)
                token_response = auth_api.login_auth_token_post(
                    username=username,
                    password=password,
                )
                # Configure with access token
                configuration.access_token = token_response.access_token
                logger.info(f"Successfully authenticated as {username}")
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise ValueError(f"Failed to authenticate with leaderboard API: {e}")

        return configuration

    def _register_agent(self):
        """
        Register the agent with the leaderboard API or retrieve existing agent ID.

        Checks if an agent with the same name already exists on the leaderboard.
        If found, uses the existing agent's ID. If not found, registers a new agent.
        """
        with sorrydb_api_client.ApiClient(self.api_configuration) as api_client:
            # Create an instance of the API class
            api_instance = sorrydb_api_client.DefaultApi(api_client)
            skip = 0  # int |  (optional) (default to 0)
            limit = 10  # int |  (optional) (default to 10)

            try:
                # List Agents
                api_response = api_instance.list_agents_agents_get(
                    skip=skip, limit=limit
                )

                agents_with_same_name = [
                    agent for agent in api_response if agent.name == self.name
                ]
                logger.info("The response of DefaultApi->register_agent_agents_post:\n")
                logger.info(api_response)

                if len(agents_with_same_name) > 1:
                    raise ValueError("More than one agent with name.")
                elif len(agents_with_same_name) == 1:
                    logger.info(f"Agent already exists with name {self.name}")
                    self.agent_id = agents_with_same_name[0].id
                else:
                    logger.info(f"Createing new agent with name {self.name}")
                    agent_create = sorrydb_api_client.AgentCreate(name=self.name)
                    api_response = api_instance.register_agent_agents_post(
                        agent_create
                    )
                    self.agent_id = api_response.id

            except Exception as e:
                logger.error(
                    "Exception when calling DefaultApi->list_agents_agents_get: %s\n"
                    % e
                )

    def attempt_challenge(self):
        """
        Request a challenge from the leaderboard, attempt to solve it, and submit the proof.

        Workflow:
            1. Request a challenge (sorry) from the leaderboard API
            2. Clone/prepare the repository at the specified commit
            3. Use the strategy to generate a proof
            4. Verify the proof builds correctly
            5. Submit the verified proof to the leaderboard

        The proof is only submitted if it passes verification. If the strategy
        returns no proof or if verification fails, no submission is made.
        """
        with sorrydb_api_client.ApiClient(self.api_configuration) as api_client:
            api_instance = sorrydb_api_client.DefaultApi(api_client)
            request_challenge_response = (
                api_instance.request_sorry_challenge_agents_agent_id_challenges_post(
                    self.agent_id
                )
            )
            sql_sorry = request_challenge_response.sorry
            logger.info(f"recieved sorry from Leaderboard api:{sql_sorry}")
            database_sorry = Sorry.from_sql_sorry(sql_sorry)

            checkout_path = ensure_repo_is_prepared(
                database_sorry.repo.remote,
                database_sorry.repo.commit,
                self.lean_data_path,
                database_sorry.repo.lean_version,
            )
            proof = self.strategy.prove_sorry(checkout_path, database_sorry)
            logger.info(f"Agent generated proof: {proof}")

            if proof:
                proof_verified = verify_proof(
                    checkout_path,
                    database_sorry.repo.lean_version,
                    database_sorry.location,
                    proof,
                )

                if proof_verified:
                    challenge_submission_create = (
                        sorrydb_api_client.ChallengeSubmissionCreate(proof=proof)
                    )

                    submit_challenge_response = api_instance.submit_proof_agents_agent_id_challenges_challenge_id_submit_post(
                        self.agent_id,
                        request_challenge_response.id,
                        challenge_submission_create,
                    )

                    logger.info(
                        f"Recieve reponse from submitting challenge {submit_challenge_response}"
                    )
