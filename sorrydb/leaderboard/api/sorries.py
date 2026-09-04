import logging
from datetime import datetime
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, BeforeValidator

from sorrydb.database.sorry import Sorry
from sorrydb.leaderboard.api.app_config import get_logger, get_repository
from sorrydb.leaderboard.api.dependencies import get_current_admin_user
from sorrydb.leaderboard.database.postgres_database import SQLDatabase
from sorrydb.leaderboard.model.challenge import ChallengeStatus
from sorrydb.leaderboard.model.sorry import SorrySortField, SortOrder
from sorrydb.leaderboard.model.user import User
from sorrydb.leaderboard.services import sorry_service
from sorrydb.leaderboard.services.sorry_service import SorryNotFound

router = APIRouter()

# a page big enough to be useful without letting a client ask for the whole table
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def _blank_as(default):
    """Treat a blank query parameter as if it had not been supplied.

    A filter form that submits an empty field means "no filter", not "match the
    empty string". Applied to every optional parameter so they all agree, rather
    than some filtering on "" and the typed ones rejecting the request.
    """
    return BeforeValidator(lambda value: default if value == "" else value)


class SorryRead(BaseModel):
    id: str
    remote: str
    branch: str
    commit: str
    lean_version: str
    path: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    goal: str
    url: str
    blame_email_hash: str
    blame_date: datetime
    inclusion_date: datetime
    solved: bool


class SorryPage(BaseModel):
    items: List[SorryRead]
    total: int
    limit: int
    offset: int


class SorryChallengeRead(BaseModel):
    id: str
    agent_id: Optional[str]
    agent_name: Optional[str]
    # the challenge.status column is nullable, so this must allow null too
    status: Optional[ChallengeStatus]
    deadline: datetime
    submission: Optional[str]


class SorryDetail(SorryRead):
    challenges: List[SorryChallengeRead]


class RemoteCount(BaseModel):
    remote: str
    count: int


class LeanVersionCount(BaseModel):
    lean_version: str
    count: int


class MonthCount(BaseModel):
    month: str  # YYYY-MM
    count: int


class SorryStats(BaseModel):
    total: int
    solved: int
    unsolved: int
    by_remote: List[RemoteCount]
    by_lean_version: List[LeanVersionCount]
    by_blame_month: List[MonthCount]
    by_inclusion_month: List[MonthCount]


class SorryFilterOptions(BaseModel):
    remotes: List[str]
    lean_versions: List[str]


class SorryReplaceResult(BaseModel):
    stored: int
    retired: int


@router.put("/sorries/", response_model=SorryReplaceResult)
async def replace_sorries(
    sorries: List[Sorry],
    logger: Annotated[logging.Logger, Depends(get_logger)],
    leaderboard_repo: Annotated[SQLDatabase, Depends(get_repository)],
    _admin: Annotated[User, Depends(get_current_admin_user)],
):
    """Replace the stored sorry set with the posted one.

    PUT rather than POST because the body is the whole latest dataset, not an
    addition to it: a sorry already stored but absent from the body is retired.
    That is also why it is admin only. An unauthenticated caller could once
    insert junk; against a replace they could retire the entire dataset.
    """
    return sorry_service.replace_sorries(sorries, logger, leaderboard_repo)


@router.get("/sorries/", response_model=SorryPage)
async def list_sorries(
    leaderboard_repo: Annotated[SQLDatabase, Depends(get_repository)],
    limit: Annotated[
        int, _blank_as(DEFAULT_PAGE_SIZE), Query(ge=1, le=MAX_PAGE_SIZE)
    ] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, _blank_as(0), Query(ge=0)] = 0,
    remote: Annotated[
        Optional[str],
        _blank_as(None),
        Query(description="Filter to one repository remote"),
    ] = None,
    lean_version: Annotated[Optional[str], _blank_as(None), Query()] = None,
    blame_date_from: Annotated[Optional[datetime], _blank_as(None), Query()] = None,
    blame_date_to: Annotated[Optional[datetime], _blank_as(None), Query()] = None,
    solved: Annotated[
        Optional[bool],
        _blank_as(None),
        Query(description="Filter to sorries with or without a successful challenge"),
    ] = None,
    sort_by: Annotated[
        SorrySortField,
        _blank_as(SorrySortField.inclusion_date),
        Query(),
    ] = SorrySortField.inclusion_date,
    sort_order: Annotated[
        SortOrder, _blank_as(SortOrder.desc), Query()
    ] = SortOrder.desc,
):
    """Paginated list of sorries with the total number matching the filters."""
    return sorry_service.list_sorries(
        leaderboard_repo,
        limit=limit,
        offset=offset,
        remote=remote,
        lean_version=lean_version,
        blame_date_from=blame_date_from,
        blame_date_to=blame_date_to,
        solved=solved,
        sort_by=sort_by,
        sort_order=sort_order,
    )


# declared before /sorries/{sorry_id} so that the literal paths are matched first
@router.get("/sorries/stats", response_model=SorryStats)
async def get_sorry_stats(
    leaderboard_repo: Annotated[SQLDatabase, Depends(get_repository)],
):
    """Aggregate counts over the current sorry set, grouped by the database."""
    return sorry_service.get_sorry_stats(leaderboard_repo)


@router.get("/sorries/filter-options", response_model=SorryFilterOptions)
async def get_sorry_filter_options(
    leaderboard_repo: Annotated[SQLDatabase, Depends(get_repository)],
):
    """Distinct values for the list filters, for populating dropdowns."""
    return sorry_service.get_filter_options(leaderboard_repo)


@router.get("/sorries/{sorry_id}", response_model=SorryDetail)
async def get_sorry(
    sorry_id: str,
    logger: Annotated[logging.Logger, Depends(get_logger)],
    leaderboard_repo: Annotated[SQLDatabase, Depends(get_repository)],
):
    """A single sorry together with the challenges agents have made against it."""
    try:
        return sorry_service.get_sorry_detail(sorry_id, logger, leaderboard_repo)
    except SorryNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
