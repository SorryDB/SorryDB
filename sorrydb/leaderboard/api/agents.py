import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

import sorrydb.leaderboard.services.agent_services as agent_services
from sorrydb.leaderboard.api.app_config import get_logger, get_repository
from sorrydb.leaderboard.database.postgres_database import SQLDatabase

router = APIRouter()


class AgentCreate(BaseModel):
    name: str


class AgentRead(BaseModel):
    id: str
    name: str


@router.post("/agents/", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def register_agent(
    agent_create: AgentCreate,
    logger: Annotated[logging.Logger, Depends(get_logger)],
    leaderboard_repo: Annotated[SQLDatabase, Depends(get_repository)],
):
    """
    Register an new agent to compete on the SorryDB Leaderboard.
    """
    return agent_services.register_agent(agent_create.name, logger, leaderboard_repo)


@router.get("/agents/", response_model=list[AgentRead])
async def list_agents(
    logger: Annotated[logging.Logger, Depends(get_logger)],
    leaderboard_repo: Annotated[SQLDatabase, Depends(get_repository)],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    """
    List all agents.
    """
    return agent_services.list_agents(logger, leaderboard_repo, skip, limit)
