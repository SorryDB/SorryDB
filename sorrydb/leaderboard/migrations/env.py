import os

from alembic import context
from sqlmodel import SQLModel, create_engine

# importing the models registers their tables on SQLModel.metadata, which is what
# `alembic revision --autogenerate` compares the database against
from sorrydb.leaderboard.model.agent import Agent  # noqa: F401
from sorrydb.leaderboard.model.challenge import Challenge  # noqa: F401
from sorrydb.leaderboard.model.sorry import SQLSorry  # noqa: F401
from sorrydb.leaderboard.model.user import User  # noqa: F401

config = context.config
target_metadata = SQLModel.metadata


def get_database_url() -> str:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set.")
    return database_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_database_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
