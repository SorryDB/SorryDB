import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from sorrydb.leaderboard.api import sorries
import sorrydb.leaderboard.api.agents as agents
import sorrydb.leaderboard.api.auth as auth
import sorrydb.leaderboard.api.challenges as challenges
from sorrydb.leaderboard.api.postgres_database_session import (
    connect_to_db,
    create_db_and_tables,
)

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Connecting to database...")
    connect_to_db()
    logger.info("Creating database and tables...")
    create_db_and_tables()

    yield
    logger.info("Application shutting down.")


app = FastAPI(
    lifespan=lifespan,
    license_info={
        "name": "Apache-2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
)

app.include_router(auth.router)
app.include_router(challenges.router)
app.include_router(agents.router)
app.include_router(sorries.router)
