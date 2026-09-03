import logging
import os
from pathlib import Path
from typing import Annotated

from alembic import command
from alembic.config import Config
from fastapi import Depends
from sqlalchemy import Engine, inspect
from sqlmodel import Session, create_engine

# The engine will be initialized during the application startup
# TODO: might we should make this a class since it shares the engine?
engine: Engine | None = None


def connect_to_db():
    """Connect to the database and initialize the engine."""
    global engine
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set.")
    engine = create_engine(database_url, echo=True)


# the first migration, which creates the schema as it was before alembic existed
BASELINE_REVISION = "e8bea6841fdb"


def _alembic_config() -> Config:
    """Point alembic at the migrations shipped inside the package."""
    config = Config()
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    config.set_main_option("script_location", str(migrations))
    return config


def run_migrations():
    """Bring the database schema up to date.

    Databases created before alembic was introduced already hold the baseline
    tables but no alembic_version row. Stamping them with the baseline revision
    first means the outstanding migrations apply instead of failing on tables
    that are already there.
    """
    logger = logging.getLogger("uvicorn.error")
    assert engine is not None, (
        "Database engine not initialized. Call connect_to_db() first."
    )
    config = _alembic_config()

    tables = set(inspect(engine).get_table_names())
    if "sqlsorry" in tables and "alembic_version" not in tables:
        logger.info("Stamping pre-alembic database with revision %s", BASELINE_REVISION)
        command.stamp(config, BASELINE_REVISION)

    logger.info("Applying database migrations")
    command.upgrade(config, "head")


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
