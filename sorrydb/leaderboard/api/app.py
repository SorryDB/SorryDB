import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

import sorrydb.leaderboard.api.agents as agents
import sorrydb.leaderboard.api.challenges as challenges
from sorrydb.leaderboard.api.postgres_database_session import (
    connect_to_db,
    create_db_and_tables,
    get_session,
)
from sorrydb.leaderboard.database.postgres_database import PostgresDatabase
from sorrydb.leaderboard.services.sorry_selector_service import select_sample_sorry

logger = logging.getLogger("uvicorn.error")

# Set this true to load a test sorry into the leaderboard database on start up
# This is a workaround until we have a proper way of loading
LOAD_TEST_SORRY = False


# The lifespan context manager handles setup and teardown for the entire
# FastAPI application
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once on startup
    logger.info("Connecting to database...")
    connect_to_db()
    logger.info("Creating database and tables...")
    create_db_and_tables()

    if LOAD_TEST_SORRY:
        load_test_sorry()

    yield
    # Runs once on shutdown
    logger.info("Application shutting down.")


def load_test_sorry():
    session = next(get_session())

    repo = PostgresDatabase(session)

    repo.add_sorry(select_sample_sorry())


app = FastAPI(lifespan=lifespan)

app.include_router(challenges.router)
app.include_router(agents.router)
