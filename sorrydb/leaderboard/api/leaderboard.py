import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from sorrydb.leaderboard.api.app_config import get_logger, get_repository
from sorrydb.leaderboard.database.postgres_database import SQLDatabase

router = APIRouter()


class LeaderboardEntry(BaseModel):
    rank: int
    agent_id: str
    agent_name: str
    completed_challenges: int


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def get_leaderboard(
    logger: Annotated[logging.Logger, Depends(get_logger)],
    leaderboard_repo: Annotated[SQLDatabase, Depends(get_repository)],
    limit: int = Query(100, ge=1, le=500, description="Number of top agents to return"),
):
    """
    Public endpoint to get the leaderboard of agents ranked by completed challenges.
    No authentication required.
    """
    logger.info(f"Fetching leaderboard with limit {limit}")

    results = leaderboard_repo.get_leaderboard(limit=limit)

    leaderboard = []
    for rank, (agent_id, agent_name, completed_challenges) in enumerate(results, start=1):
        leaderboard.append(
            LeaderboardEntry(
                rank=rank,
                agent_id=agent_id,
                agent_name=agent_name,
                completed_challenges=completed_challenges,
            )
        )

    return leaderboard
