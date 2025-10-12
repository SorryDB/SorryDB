import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

from sorrydb.leaderboard.api.postgres_database_session import (
    SessionDep,
)
from sorrydb.leaderboard.database.postgres_database import SQLDatabase


class Settings(BaseSettings):
    secret_key: str = "dev_secret_key_change_in_production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


def get_repository(session: SessionDep):
    """
    Configure the leaderboard repository.
    """
    return SQLDatabase(session)


# use `uvicorn.error` logger so that log messages are printed to uvicorn logs.
# TODO: We should probably configure our own application logging separately from uvicorn logs
logger = logging.getLogger("uvicorn.error")


def get_logger():
    return logger
