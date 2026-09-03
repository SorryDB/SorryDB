import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

from alembic import command
from alembic.config import Config
from fastapi import Depends
from sqlalchemy import Engine, inspect, text
from sqlmodel import Session, SQLModel, create_engine

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
MIGRATION_LOCK_TIMEOUT_SECONDS = 60


@contextmanager
def _migration_lock():
    """Hold a Postgres advisory lock for the duration of the migration run.

    Cloud Run starts several instances at once and alembic takes no lock of its
    own, so without this two cold starts can both try to stamp the version table
    or create the same index, and the one that loses dies during startup.

    The wait is bounded. `pg_advisory_lock` would block forever, and because
    this runs inside the startup handler a stuck holder would leave every other
    instance hanging until it was killed. Giving up with an error instead lets
    the instance restart and try again.
    """
    if engine.dialect.name != "postgresql":
        yield
        return

    with engine.connect() as connection:
        deadline = time.monotonic() + MIGRATION_LOCK_TIMEOUT_SECONDS
        while True:
            acquired = connection.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": MIGRATION_LOCK_KEY}
            ).scalar()
            # commit so that holding the lock does not also hold a transaction open
            connection.commit()
            if acquired:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "Another instance has held the migration lock for more than "
                    f"{MIGRATION_LOCK_TIMEOUT_SECONDS}s. Giving up so this instance "
                    "restarts rather than blocking startup indefinitely."
                )
            time.sleep(1)
        try:
            yield
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK_KEY}
            )
            connection.commit()


def _assert_no_schema_drift():
    """Refuse to stamp a database whose schema is not actually the baseline.

    Stamping records a database as up to date, so a column that `create_all`
    failed to add would stay missing for good and every query touching it would
    fail at runtime. None of the migrations add a column, so anything the models
    declare and the database lacks is pre-existing drift. Naming it and stopping
    is better than freezing it in place.
    """
    # importing the models is what registers their tables on SQLModel.metadata,
    # and nothing else in this module pulls them in
    from sorrydb.leaderboard.model.agent import Agent  # noqa: F401
    from sorrydb.leaderboard.model.challenge import Challenge  # noqa: F401
    from sorrydb.leaderboard.model.sorry import SQLSorry  # noqa: F401
    from sorrydb.leaderboard.model.user import User  # noqa: F401

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    assert SQLModel.metadata.sorted_tables, "no models registered on the metadata"

    missing = []
    for table in SQLModel.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        present = {column["name"] for column in inspector.get_columns(table.name)}
        missing += [
            f"{table.name}.{column.name}"
            for column in table.columns
            if column.name not in present
        ]

    if missing:
        raise RuntimeError(
            "This database predates alembic and is missing columns that "
            f"create_all could not add: {', '.join(sorted(missing))}. "
            "Add them by hand, then restart so that the baseline stamp is accurate."
        )


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
            _assert_no_schema_drift()
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
