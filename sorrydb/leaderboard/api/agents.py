import logging
from typing import Annotated

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

import sorrydb.leaderboard.services.agent_services as agent_services
from sorrydb.leaderboard.api.app_config import get_logger, get_repository
from sorrydb.leaderboard.api.dependencies import get_current_active_user
from sorrydb.leaderboard.database.postgres_database import SQLDatabase
from sorrydb.leaderboard.model.user import User

router = APIRouter()


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    visible: bool = True
    min_lean_version: Optional[str] = None
    max_lean_version: Optional[str] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    visible: Optional[bool] = None
    min_lean_version: Optional[str] = None
    max_lean_version: Optional[str] = None


class AgentRead(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    visible: bool
    min_lean_version: Optional[str] = None
    max_lean_version: Optional[str] = None


@router.post("/agents/", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def register_agent(
    agent_create: AgentCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    logger: Annotated[logging.Logger, Depends(get_logger)],
    leaderboard_repo: Annotated[SQLDatabase, Depends(get_repository)],
):
    return agent_services.register_agent(
        agent_create, current_user.id, logger, leaderboard_repo
    )


@router.get("/agents/", response_model=list[AgentRead])
async def list_agents(
    current_user: Annotated[User, Depends(get_current_active_user)],
    logger: Annotated[logging.Logger, Depends(get_logger)],
    leaderboard_repo: Annotated[SQLDatabase, Depends(get_repository)],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    return agent_services.list_agents(
        current_user.id, logger, leaderboard_repo, skip, limit
    )


@router.get("/agents/{agent_id}", response_model=AgentRead)
async def get_agent(
    agent_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    leaderboard_repo: Annotated[SQLDatabase, Depends(get_repository)],
):
    agent = leaderboard_repo.get_agent(agent_id)
    if agent.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return agent


@router.patch("/agents/{agent_id}", response_model=AgentRead)
async def update_agent(
    agent_id: str,
    agent_update: AgentUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    logger: Annotated[logging.Logger, Depends(get_logger)],
    leaderboard_repo: Annotated[SQLDatabase, Depends(get_repository)],
):
    return agent_services.update_agent(
        agent_id, agent_update, current_user.id, logger, leaderboard_repo
    )
