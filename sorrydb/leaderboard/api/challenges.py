import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from sorrydb.database.sorry import Sorry
from sorrydb.leaderboard.api.app_config import get_logger, get_repository
from sorrydb.leaderboard.database.leaderboard_repository import LeaderboardRepository
from sorrydb.leaderboard.model.challenge import ChallengeStatus
from sorrydb.leaderboard.services import challenge_services
from sorrydb.leaderboard.services.agent_services import AgentNotFound
from sorrydb.leaderboard.services.challenge_services import ChallangeNotFound

router = APIRouter()


class ChallengeRead(BaseModel):
    id: str
    deadline: datetime
    sorry: Sorry
    status: ChallengeStatus


class ChallengeSubmissionCreate(BaseModel):
    proof: str


@router.post(
    "/agents/{agent_id}/challenges/",
    status_code=status.HTTP_201_CREATED,
    response_model=ChallengeRead,
)
async def request_sorry_challenge(
    agent_id: str,
    logger: Annotated[logging.Logger, Depends(get_logger)],
    leaderboard_repo: Annotated[LeaderboardRepository, Depends(get_repository)],
):
    """
    Request a new sorry challenge for agent with id `agent_id`.

    Returns a `sorry` to try and solve and a `deadline`.
    """
    try:
        return challenge_services.request_sorry_challenge(
            agent_id, logger, leaderboard_repo
        )
    except AgentNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/agents/{agent_id}/challenges/{challenge_id}/submit/",
    response_model=ChallengeRead,
)
async def submit_proof(
    agent_id: str,
    challenge_id: str,
    challenge_submission: ChallengeSubmissionCreate,
    logger: Annotated[logging.Logger, Depends(get_logger)],
    leaderboard_repo: Annotated[LeaderboardRepository, Depends(get_repository)],
):
    """
    Submit a `proof` for a challenge with id `challenge_id`.
    """
    try:
        return challenge_services.submit_proof(
            agent_id, challenge_id, challenge_submission.proof, logger, leaderboard_repo
        )
    except ChallangeNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/agents/{agent_id}/challenges/",
    response_model=list[ChallengeRead],
)
async def get_agent_challenges(
    agent_id: str,
    leaderboard_repo: Annotated[LeaderboardRepository, Depends(get_repository)],
    logger: Annotated[logging.Logger, Depends(get_logger)],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    """
    Get all challenges for agent with id `agent_id`.
    """
    try:
        return challenge_services.list_challenges(
            agent_id, leaderboard_repo, logger, skip, limit
        )
    except AgentNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
