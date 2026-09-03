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
