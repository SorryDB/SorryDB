import os
from logging.config import fileConfig

from alembic import context
from sqlmodel import SQLModel, create_engine

# importing the models registers their tables on SQLModel.metadata, which is what
# `alembic revision --autogenerate` compares the database against
from sorrydb.leaderboard.model.agent import Agent  # noqa: F401
from sorrydb.leaderboard.model.challenge import Challenge  # noqa: F401
from sorrydb.leaderboard.model.sorry import SQLSorry  # noqa: F401
from sorrydb.leaderboard.model.user import User  # noqa: F401

config = context.config

# only set when alembic is driven from alembic.ini on the command line. The app
# builds a Config() with no file, and then keeps its own logging setup.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

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
    # the application passes in the connection holding the migration lock, so
    # that the migration runs on the same session the lock belongs to
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

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
