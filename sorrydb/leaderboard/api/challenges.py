import logging
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from sorrydb.leaderboard.api.app_config import get_logger, get_repository
from sorrydb.leaderboard.api.dependencies import get_current_active_user
from sorrydb.leaderboard.database.postgres_database import SQLDatabase
from sorrydb.leaderboard.model.challenge import ChallengeStatus
from sorrydb.leaderboard.model.sorry import SQLSorry
from sorrydb.leaderboard.model.user import User
from sorrydb.leaderboard.services import challenge_services
from sorrydb.leaderboard.services.agent_services import AgentNotFound
from sorrydb.leaderboard.services.challenge_services import ChallengeNotFound
from sorrydb.leaderboard.services.sorry_service import NoSorryError

router = APIRouter()


def verify_agent_ownership(agent_id: str, user_id: str, db: SQLDatabase):
    try:
        agent = db.get_agent(agent_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    if agent.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this agent",
        )


class ChallengeRead(BaseModel):
    id: str
    deadline: datetime
    sorry: SQLSorry
    status: ChallengeStatus
    submission: Optional[str]


class ChallengeSubmissionCreate(BaseModel):
    proof: str


@router.post(
    "/agents/{agent_id}/challenges/",
    status_code=status.HTTP_201_CREATED,
    response_model=ChallengeRead,
)
async def request_sorry_challenge(
    agent_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    logger: Annotated[logging.Logger, Depends(get_logger)],
    leaderboard_repo: Annotated[SQLDatabase, Depends(get_repository)],
):
    try:
        verify_agent_ownership(agent_id, current_user.id, leaderboard_repo)
        return challenge_services.request_sorry_challenge(
            agent_id, logger, leaderboard_repo
        )
    except AgentNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NoSorryError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post(
    "/agents/{agent_id}/challenges/{challenge_id}/submit/",
    response_model=ChallengeRead,
)
async def submit_proof(
    agent_id: str,
    challenge_id: str,
    challenge_submission: ChallengeSubmissionCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    logger: Annotated[logging.Logger, Depends(get_logger)],
    leaderboard_repo: Annotated[SQLDatabase, Depends(get_repository)],
):
    try:
        verify_agent_ownership(agent_id, current_user.id, leaderboard_repo)
        return challenge_services.submit_proof(
            agent_id, challenge_id, challenge_submission.proof, logger, leaderboard_repo
        )
    except ChallengeNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/agents/{agent_id}/challenges/",
    response_model=list[ChallengeRead],
)
async def get_agent_challenges(
    agent_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    leaderboard_repo: Annotated[SQLDatabase, Depends(get_repository)],
    logger: Annotated[logging.Logger, Depends(get_logger)],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    try:
        verify_agent_ownership(agent_id, current_user.id, leaderboard_repo)
        return challenge_services.list_challenges(
            agent_id, leaderboard_repo, logger, skip, limit
        )
    except AgentNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
