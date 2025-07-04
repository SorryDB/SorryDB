import logging
import os
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine
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


def create_db_and_tables():
    """Create database tables."""
    logger = logging.getLogger("uvicorn.error")
    assert engine is not None, (
        "Database engine not initialized. Call connect_to_db() first."
    )
    table_names = list(SQLModel.metadata.tables.keys())
    logger.info(f"Tables to be created: {table_names}")
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
