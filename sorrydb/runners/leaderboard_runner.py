import logging
from pathlib import Path

import sorrydb_api_client
from git import Repo

from sorrydb.runners.json_runner import SorryStrategy
from sorrydb.database.sorry import Sorry
from sorrydb.utils.verify import verify_proof

logger = logging.getLogger(__name__)

api_sdk_configuration = sorrydb_api_client.Configuration(host="http://127.0.0.1:8000")


class LeaderboardRunner:
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

        self._register_agent()

    # TODO: THis was copied from the agent comparison agent and shouldn't be duplicated
    def _ensure_repo_is_prepared(
        self,
        remote_url: str,
        commit: str,
        lean_data: Path,
        lean_version: str,
    ) -> Path:
        # Create a directory name from the remote URL
        repo_name = remote_url.rstrip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        checkout_path = lean_data / repo_name / lean_version / commit
        if not checkout_path.exists():
            logger.info(f"Cloning {remote_url}")
            repo = Repo.clone_from(remote_url, checkout_path)
            logger.info(f"Checking out {repo_name} repo at commit {commit}")
            repo.git.checkout(commit)
        else:
            logger.info(
                f"Repo {repo_name} with version {lean_version} on commit {commit} already exists at {checkout_path}"
            )
            repo = Repo(checkout_path)

        return checkout_path

    def _register_agent(self):
        with sorrydb_api_client.ApiClient(api_sdk_configuration) as api_client:
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
                    api_response = api_instance.register_agent_agents_post(
                        AgentCreate(name=self.name)
                    )

            except Exception as e:
                logger.error(
                    "Exception when calling DefaultApi->list_agents_agents_get: %s\n"
                    % e
                )

    def attempt_challenge(self):
        with sorrydb_api_client.ApiClient(api_sdk_configuration) as api_client:
            api_instance = sorrydb_api_client.DefaultApi(api_client)
            request_challenge_response = (
                api_instance.request_sorry_challenge_agents_agent_id_challenges_post(
                    self.agent_id
                )
            )
            sql_sorry = request_challenge_response.sorry
            logger.info(f"recieved sorry from Leaderboard api:{sql_sorry}")
            database_sorry = Sorry.from_sql_sorry(sql_sorry)

            checkout_path = self._ensure_repo_is_prepared(
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
