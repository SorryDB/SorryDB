from logging import Logger

from sorrydb.leaderboard.database.postgres_database import SQLDatabase
from sorrydb.leaderboard.model.sorry import SQLSorry


class NoSorryError(Exception):
    pass


# TODO: create a better sorry selection algorithm
def select_sorry(logger: Logger, repo: SQLDatabase) -> SQLSorry:
    if not (sorry := repo.get_sorry()):
        msg = "No sorry to serve"
        logger.error(msg)
        raise NoSorryError
    else:
        return sorry
