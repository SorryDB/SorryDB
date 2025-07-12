import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

import sorrydb.leaderboard.api.agents as agents
import sorrydb.leaderboard.api.challenges as challenges
from sorrydb.leaderboard.api.postgres_database_session import (
    connect_to_db,
    create_db_and_tables,
)

logger = logging.getLogger("uvicorn.error")


# The lifespan context manager handles setup and teardown for the entire
# FastAPI application
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once on startup
    logger.info("Connecting to database...")
    connect_to_db()
    logger.info("Creating database and tables...")
    create_db_and_tables()

    yield
    # Runs once on shutdown
    logger.info("Application shutting down.")


app = FastAPI(lifespan=lifespan)

app.include_router(challenges.router)
app.include_router(agents.router)
