from logging import Logger

from sorrydb.database.sorry import Sorry
from sorrydb.leaderboard.database.postgres_database import SQLDatabase
from sorrydb.leaderboard.model.agent import Agent
from sorrydb.leaderboard.model.sorry import SQLSorry


class NoSorryError(Exception):
    pass


# TODO: create a better sorry selection algorithm
def select_sorry(agent: Agent, logger: Logger, repo: SQLDatabase) -> SQLSorry:
    if not (sorry := repo.get_latest_unattempted_sorry(agent)):
        msg = "No sorry to serve"
        logger.error(msg)
        raise NoSorryError(msg)
    else:
        return sorry


def add_sorry(sorry: Sorry, logger: Logger, repo: SQLDatabase) -> SQLSorry:
    sqlsorry = SQLSorry.from_json_sorry(sorry)
    repo.add_sorry(sqlsorry)
    logger.info(f"Added new sorry with id {sqlsorry.id}")
    return sqlsorry


def add_sorries(
    sorries: list[Sorry], logger: Logger, repo: SQLDatabase
) -> list[SQLSorry]:
    sql_sorries = [SQLSorry.from_json_sorry(s) for s in sorries]
    logger.info(f"Batch adding new sorries with ids {[s.id for s in sql_sorries]}")
    repo.add_sorries(sql_sorries)
    logger.info("Batch add successful")
    return sql_sorries
