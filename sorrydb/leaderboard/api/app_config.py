import logging

from sorrydb.leaderboard.database.database import InMemoryLeaderboardDatabase

# Global instance of the in-memory database
# This will be shared across requests for the lifetime of the app/test session
_db_instance = InMemoryLeaderboardDatabase()


# TODO: Once we have a proper database this function will determine if we
# should use the fake in-memory database or the real database.
# For now, it simply returns the in-memory database
def get_repository():
    """
    Configure the leaderboard repository.
    """
    return _db_instance


# use `uvicorn.error` logger so that log messages are printed to uvicorn logs.
# TODO: We should probably configure our own application logging separately from uvicorn logs
logger = logging.getLogger("uvicorn.error")


def get_logger():
    return logger
