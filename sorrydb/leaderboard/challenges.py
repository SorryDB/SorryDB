import logging
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import APIRouter, FastAPI, status
from pydantic import BaseModel, Field

from sorrydb.database.sorry import Sorry
from sorrydb.leaderboard.model.challenge import ChallengeStatus
from sorrydb.leaderboard.sorry_selector import select_sample_sorry

router = APIRouter()

# use `uvicorn.error` logger so that log messages are printed to uvicorn logs.
# TODO: We should probably configure our own application logging separately from uvicorn logs
logger = logging.getLogger("uvicorn.error")


class ChallengeRead(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    deadline: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=1)
    )
    sorry: Sorry
    status: ChallengeStatus = ChallengeStatus.AWAITING_SUBMISSION


class ChallengeSubmissionCreate(BaseModel):
    proof: str


@router.post("/agents/{agent_id}/challenges/", status_code=status.HTTP_201_CREATED)
async def new_challenge(agent_id: str) -> ChallengeRead:
    challenge = ChallengeRead(sorry=select_sample_sorry())
    logger.info(
        f"Created new sample challege with id {challenge.id} for agent {agent_id}"
    )
    return challenge


@router.post("/agents/{agent_id}/challenges/{challenge_id}/submit/")
async def submit_proof(
    agent_id: str, challenge_id: str, challenge_submission: ChallengeSubmissionCreate
) -> ChallengeRead:
    logger.info(
        f"Received proof: {challenge_submission.proof} for agent {agent_id} and challenge {challenge_id}"
    )
    # For now, create a dummy challenge response with submitted status
    challenge = ChallengeRead(
        sorry=select_sample_sorry(), status=ChallengeStatus.PENDING_VERIFICATION
    )
    challenge.id = challenge_id
    return challenge
