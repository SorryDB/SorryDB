import logging
from typing import Annotated, List

from fastapi import APIRouter, Depends, status

from sorrydb.database.sorry import Sorry
from sorrydb.leaderboard.api.app_config import get_logger, get_repository
from sorrydb.leaderboard.database.postgres_database import SQLDatabase
from sorrydb.leaderboard.services import sorry_service

router = APIRouter()


@router.post("/sorries/", status_code=status.HTTP_201_CREATED)
async def add_sorry(
    sorries: Sorry | List[Sorry],
    logger: Annotated[logging.Logger, Depends(get_logger)],
    leaderboard_repo: Annotated[SQLDatabase, Depends(get_repository)],
):
    if isinstance(sorries, list):
        return sorry_service.add_sorries(sorries, logger, leaderboard_repo)
    return sorry_service.add_sorry(sorries, logger, leaderboard_repo)
