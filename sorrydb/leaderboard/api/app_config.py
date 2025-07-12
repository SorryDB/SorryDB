import logging

from sorrydb.leaderboard.api.postgres_database_session import (
    SessionDep,
)
from sorrydb.leaderboard.database.postgres_database import PostgresDatabase


def get_repository(session: SessionDep):
    """
    Configure the leaderboard repository.
    """
    return PostgresDatabase(session)


# use `uvicorn.error` logger so that log messages are printed to uvicorn logs.
# TODO: We should probably configure our own application logging separately from uvicorn logs
logger = logging.getLogger("uvicorn.error")


def get_logger():
    return logger
