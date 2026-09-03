import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

from alembic import command
from alembic.config import Config
from fastapi import Depends
from sqlalchemy import Engine, inspect, text
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

# an arbitrary but fixed key, so every instance contends for the same lock
MIGRATION_LOCK_KEY = 8675309


@contextmanager
def _migration_lock():
    """Hold a Postgres advisory lock for the duration of the migration run.

    Cloud Run starts several instances at once and alembic takes no lock of its
    own, so without this two cold starts can both try to stamp the version table
    or create the same index, and the one that loses dies during startup.
    """
    if engine.dialect.name != "postgresql":
        yield
        return

    with engine.connect() as connection:
        connection.execute(
            text("SELECT pg_advisory_lock(:key)"), {"key": MIGRATION_LOCK_KEY}
        )
        # commit so that holding the lock does not also hold a transaction open
        connection.commit()
        try:
            yield
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK_KEY}
            )
            connection.commit()


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

    with _migration_lock():
        tables = set(inspect(engine).get_table_names())
        if "sqlsorry" in tables and "alembic_version" not in tables:
            logger.info(
                "Stamping pre-alembic database with revision %s", BASELINE_REVISION
            )
            command.stamp(config, BASELINE_REVISION)

        logger.info("Applying database migrations")
        command.upgrade(config, "head")


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
