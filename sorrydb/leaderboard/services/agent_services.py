import uuid
from logging import Logger

from fastapi import HTTPException, status

from sorrydb.leaderboard.database.postgres_database import SQLDatabase
from sorrydb.leaderboard.model.agent import Agent


class AgentNotFound(Exception):
    pass


def register_agent(agent_create, user_id: str, logger: Logger, repo: SQLDatabase) -> Agent:
    new_agent = Agent(
        id=str(uuid.uuid4()),
        name=agent_create.name,
        user_id=user_id,
        description=agent_create.description,
        visible=agent_create.visible,
        min_lean_version=agent_create.min_lean_version,
        max_lean_version=agent_create.max_lean_version,
    )
    repo.add_agent(new_agent)
    logger.info(f"Created new agent with id {new_agent.id} and name '{new_agent.name}'")
    return new_agent


def update_agent(
    agent_id: str, agent_update, user_id: str, logger: Logger, repo: SQLDatabase
) -> Agent:
    agent = repo.get_agent(agent_id)
    if agent.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    
    if agent_update.name is not None:
        agent.name = agent_update.name
    if agent_update.description is not None:
        agent.description = agent_update.description
    if agent_update.visible is not None:
        agent.visible = agent_update.visible
    if agent_update.min_lean_version is not None:
        agent.min_lean_version = agent_update.min_lean_version
    if agent_update.max_lean_version is not None:
        agent.max_lean_version = agent_update.max_lean_version
    
    repo.update_agent(agent)
    logger.info(f"Updated agent {agent_id}")
    return agent


def list_agents(user_id: str, logger: Logger, repo: SQLDatabase, skip, limit) -> list[Agent]:
    agents = repo.get_agents_by_user(user_id, skip, limit)
    logger.info(f"Retrieved {len(agents)} agents for user {user_id}")
    return agents


def get_agent(agent_id: str, logger: Logger, repo: SQLDatabase) -> Agent:
    try:
        return repo.get_agent(agent_id)
    except Exception as e:
        msg = f"Agent not found with id {agent_id}"
        logger.info(msg)
        raise AgentNotFound(msg) from e
