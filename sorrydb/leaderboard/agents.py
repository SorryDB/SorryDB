import logging
import uuid
from typing import List

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

router = APIRouter()

# use `uvicorn.error` logger so that log messages are printed to uvicorn logs.
# TODO: We should probably configure our own application logging separately from uvicorn logs
logger = logging.getLogger("uvicorn.error")

# Temporary in-memory storage for agents
agents = []


class AgentCreate(BaseModel):
    name: str


class AgentRead(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str


@router.post("/agents/", status_code=status.HTTP_201_CREATED)
async def create_agent(agent_create: AgentCreate) -> AgentRead:
    new_agent = AgentRead(name=agent_create.name)
    agents.append(new_agent)
    logger.info(f"Created new agent with id {new_agent.id} and name '{new_agent.name}'")
    return new_agent


@router.get("/agents/")
async def list_agents() -> List[AgentRead]:
    logger.info(f"Retrieved {len(agents)} agents")
    return agents
