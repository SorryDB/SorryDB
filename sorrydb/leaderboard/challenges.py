import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, status
from pydantic import BaseModel, Field

from sorrydb.database.sorry import Sorry
from sorrydb.leaderboard.sorry_selector import select_sample_sorry

app = FastAPI()

# use `uvicorn.error` logger so that log messages are printed to uvicorn logs.
# TODO: We should probably configure our own application logging separately from uvicorn logs
logger = logging.getLogger("uvicorn.error")


class Challenge(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    deadline: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=1)
    )
    sorry: Sorry


class ProofSubmission(BaseModel):
    proof: str


class SubmissionResponse(BaseModel):
    challenge_id: str
    status: str


@app.post("/agents/{agent_id}/challenges/", status_code=status.HTTP_201_CREATED)
async def new_challenge(agent_id: str) -> Challenge:
    challenge = Challenge(sorry=select_sample_sorry())
    logger.info(
        f"Created new sample challege with id {challenge.id} for agent {agent_id}"
    )
    return challenge


@app.post("/agents/{agent_id}/challenges/{challenge_id}/submit/")
async def submit_proof(
    agent_id: str, challenge_id: str, proof_submission: ProofSubmission
) -> SubmissionResponse:
    logger.info(
        f"Received proof: {proof_submission.proof} for agent {agent_id} and challenge {challenge_id}"
    )
    return SubmissionResponse(challenge_id=challenge_id, status="received")
