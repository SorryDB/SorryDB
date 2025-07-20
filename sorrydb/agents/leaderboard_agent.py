import logging
from pathlib import Path

from sorrydb.agents.json_agent import SorryStrategy

import sorrydb_api_client

logger = logging.getLogger(__name__)

api_sdk_configuration = sorrydb_api_client.Configuration(host="http://127.0.0.1:8000")


class LeaderboardAgent:
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

    def _list_agents(self):
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
                logger.info("The response of DefaultApi->list_agents_agents_get:\n")
                logger.info(api_response)
            except Exception as e:
                logger.error(
                    "Exception when calling DefaultApi->list_agents_agents_get: %s\n"
                    % e
                )

    # TODO: we may want to make it so that you can't register two agents with the same name
    # for a given user and then we can reuse the existing agent with this name. Currently we just register a new agent
    # with the same name.
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
                    # api_response = api_instance.register_agent_agents_post(
                    #     AgentCreate(name=self.name)
                    # )

            except Exception as e:
                logger.error(
                    "Exception when calling DefaultApi->list_agents_agents_get: %s\n"
                    % e
                )

    def attempt_challenge(self):
        pass
