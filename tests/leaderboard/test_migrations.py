"""The migration chain must build exactly the schema the models declare.

Nothing else in the suite runs the migrations: conftest builds the schema with
`SQLModel.metadata.create_all` and the app lifespan never fires under TestClient.
Without this, adding a column to a model leaves every test green while the real
startup path drifts.
"""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlmodel import SQLModel, create_engine

from sorrydb.leaderboard.api.postgres_database_session import _alembic_config


def test_migrations_reproduce_the_models(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    # env.py reads the URL from the environment
    monkeypatch.setenv("DATABASE_URL", url)

    command.upgrade(_alembic_config(), "head")

    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            difference = compare_metadata(context, SQLModel.metadata)
    finally:
        engine.dispose()

    assert difference == []


def test_migrations_create_the_analytics_indexes(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'indexed.db'}"
    monkeypatch.setenv("DATABASE_URL", url)

    command.upgrade(_alembic_config(), "head")

    engine = create_engine(url)
    try:
        from sqlalchemy import inspect

        inspector = inspect(engine)
        sorry_indexes = {i["name"] for i in inspector.get_indexes("sqlsorry")}
        challenge_indexes = {i["name"] for i in inspector.get_indexes("challenge")}
    finally:
        engine.dispose()

    assert sorry_indexes == {
        "ix_sqlsorry_remote",
        "ix_sqlsorry_lean_version",
        "ix_sqlsorry_blame_date",
        "ix_sqlsorry_inclusion_date",
    }
    assert "ix_challenge_sorry_id" in challenge_indexes


def test_a_partial_legacy_database_is_not_stamped(tmp_path, monkeypatch):
    """Stamping a database that is missing a baseline table would wedge it.

    The later migrations reference the missing table, fail, and leave the
    database stamped past the revision that would have created it, so every
    restart fails the same way.
    """
    from sqlalchemy import inspect

    from sorrydb.leaderboard.api import postgres_database_session as session_module
    from sorrydb.leaderboard.model.sorry import SQLSorry

    url = f"sqlite:///{tmp_path / 'partial.db'}"
    monkeypatch.setenv("DATABASE_URL", url)

    engine = create_engine(url)
    # a legacy database that only ever had the sorry table
    SQLSorry.__table__.create(engine)

    monkeypatch.setattr(session_module, "engine", engine)
    try:
        with pytest.raises(RuntimeError, match="Refusing to stamp"):
            session_module.run_migrations()

        # left untouched, so it can still be repaired
        assert "alembic_version" not in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


AGENT_COLUMNS_CREATE_ALL_NEVER_ADDED = (
    "visible",
    "description",
    "min_lean_version",
    "max_lean_version",
)


def test_a_legacy_agent_table_gains_the_columns_it_is_missing(tmp_path, monkeypatch):
    """The deployed database predates alembic and `agent` had drifted.

    create_all only ever creates tables, so four columns added to the model
    after the table existed were never added to it. Startup caught that and
    refused to serve, which is correct but leaves the service down until the
    chain can bring such a database up to the models by itself.

    The legacy shape is built by upgrading to the baseline and then dropping
    those four columns, rather than by create_all and undoing every later
    revision by hand. That is what a pre-alembic database looks like relative
    to the chain, and it does not need editing every time a revision is added.
    """
    from sqlalchemy import inspect, text

    from sorrydb.leaderboard.api import postgres_database_session as session_module

    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    monkeypatch.setenv("DATABASE_URL", url)

    command.upgrade(_alembic_config(), "e8bea6841fdb")

    engine = create_engine(url)
    with engine.begin() as connection:
        for name in AGENT_COLUMNS_CREATE_ALL_NEVER_ADDED:
            connection.execute(text(f"ALTER TABLE agent DROP COLUMN {name}"))
        # unstamped, so run_migrations takes the legacy path and stamps it
        connection.execute(text("DROP TABLE alembic_version"))

    monkeypatch.setattr(session_module, "engine", engine)
    try:
        session_module.run_migrations()

        present = {column["name"] for column in inspect(engine).get_columns("agent")}
    finally:
        engine.dispose()

    assert set(AGENT_COLUMNS_CREATE_ALL_NEVER_ADDED) <= present


def test_adding_those_columns_is_idempotent(tmp_path, monkeypatch):
    """A database built fresh from the baseline already has all four.

    The revision asks the inspector rather than using Postgres's
    ADD COLUMN IF NOT EXISTS, so running the chain on a database that is not
    missing anything has to be a no-op rather than a duplicate column error.
    """
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    monkeypatch.setenv("DATABASE_URL", url)

    command.upgrade(_alembic_config(), "head")
    # again, from a database already at head
    command.upgrade(_alembic_config(), "head")
