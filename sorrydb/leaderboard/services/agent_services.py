import uuid
from logging import Logger

from sorrydb.leaderboard.database.postgres_database import SQLDatabase
from sorrydb.leaderboard.model.agent import Agent


class AgentNotFound(Exception):
    pass


def register_agent(name: str, logger: Logger, repo: SQLDatabase) -> Agent:
    new_agent = Agent(id=str(uuid.uuid4()), name=name)
    repo.add_agent(new_agent)
    logger.info(f"Created new agent with id {new_agent.id} and name '{new_agent.name}'")
    return new_agent


def list_agents(logger: Logger, repo: SQLDatabase, skip, limit) -> list[Agent]:
    agents = repo.get_agents(skip, limit)
    logger.info(f"Retrieved {len(agents)} agents")
    return agents


def get_agent(agent_id: str, logger: Logger, repo: SQLDatabase) -> Agent:
    try:
        return repo.get_agent(agent_id)
    except Exception as e:
        msg = f"Agent not found with id {agent_id}"
        logger.info(msg)
        raise AgentNotFound(msg) from e
