from datetime import datetime
from logging import Logger

from sorrydb.database.sorry import Sorry
from sorrydb.leaderboard.database.postgres_database import SQLDatabase
from sorrydb.leaderboard.model.agent import Agent
from sorrydb.leaderboard.model.challenge import ChallengeStatus
from sorrydb.leaderboard.model.sorry import SorrySortField, SortOrder, SQLSorry


class NoSorryError(Exception):
    pass


def select_sorry(agent: Agent, logger: Logger, repo: SQLDatabase) -> SQLSorry:
    if not (sorry := repo.get_latest_unattempted_sorry(agent)):
        msg = "No sorry to serve"
        logger.error(msg)
        raise NoSorryError(msg)
    else:
        return sorry


def replace_sorries(sorries: list[Sorry], logger: Logger, repo: SQLDatabase) -> dict:
    """Make the stored set match the posted one, and report what changed."""
    sql_sorries = [SQLSorry.from_json_sorry(s) for s in sorries]
    logger.info(f"Replacing the sorry set with {len(sql_sorries)} sorries")
    retired = repo.replace_sorries(sql_sorries)
    logger.info(f"Replace successful, {retired} sorries retired")
    return {"stored": len(sql_sorries), "retired": retired}


class SorryNotFound(Exception):
    pass


def _sorry_with_solved(sorry: SQLSorry, solved) -> dict:
    return {**sorry.model_dump(), "solved": bool(solved)}


def _month_rows(rows) -> list[dict]:
    """Format the (year, month, count) rows the database grouped into YYYY-MM."""
    return [
        {"month": f"{int(year):04d}-{int(month):02d}", "count": count}
        for year, month, count in rows
    ]


def list_sorries(
    repo: SQLDatabase,
    limit: int,
    offset: int,
    remote: str | None = None,
    lean_version: str | None = None,
    blame_date_from: datetime | None = None,
    blame_date_to: datetime | None = None,
    solved: bool | None = None,
    sort_by: SorrySortField = SorrySortField.inclusion_date,
    sort_order: SortOrder = SortOrder.desc,
) -> dict:
    rows, total = repo.get_sorries(
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
    return {
        "items": [_sorry_with_solved(sorry, solved_flag) for sorry, solved_flag in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_sorry_detail(sorry_id: str, logger: Logger, repo: SQLDatabase) -> dict:
    sorry = repo.get_sorry(sorry_id)
    if sorry is None:
        msg = f"No sorry with id {sorry_id}"
        logger.info(msg)
        raise SorryNotFound(msg)

    challenges = [
        {**challenge.model_dump(), "agent_name": agent_name}
        for challenge, agent_name in repo.get_challenges_for_sorry(sorry_id)
    ]
    solved = any(
        challenge["status"] == ChallengeStatus.SUCCESS for challenge in challenges
    )
    return {**sorry.model_dump(), "solved": solved, "challenges": challenges}


def get_sorry_stats(repo: SQLDatabase) -> dict:
    stats = repo.get_sorry_stats()
    total = stats["total"]
    solved = stats["solved"]
    return {
        "total": total,
        "solved": solved,
        "unsolved": total - solved,
        "by_remote": [
            {"remote": remote, "count": count} for remote, count in stats["by_remote"]
        ],
        "by_lean_version": [
            {"lean_version": version, "count": count}
            for version, count in stats["by_lean_version"]
        ],
        "by_blame_month": _month_rows(stats["by_blame_month"]),
        "by_inclusion_month": _month_rows(stats["by_inclusion_month"]),
    }


def get_filter_options(repo: SQLDatabase) -> dict:
    remotes, lean_versions = repo.get_sorry_filter_options()
    return {"remotes": list(remotes), "lean_versions": list(lean_versions)}
