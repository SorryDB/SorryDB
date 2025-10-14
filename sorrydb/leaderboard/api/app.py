import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqladmin import Admin
from starlette.middleware.sessions import SessionMiddleware

from sorrydb.leaderboard.api import sorries
import sorrydb.leaderboard.api.agents as agents
import sorrydb.leaderboard.api.auth as auth
import sorrydb.leaderboard.api.challenges as challenges
import sorrydb.leaderboard.api.leaderboard as leaderboard
from sorrydb.leaderboard.api import postgres_database_session
from sorrydb.leaderboard.api.postgres_database_session import (
    connect_to_db,
    create_db_and_tables,
)
from sorrydb.leaderboard.admin.auth import AdminAuthBackend
from sorrydb.leaderboard.admin.views import (
    AgentAdmin,
    ChallengeAdmin,
    SorryAdmin,
    UserAdmin,
)

logger = logging.getLogger("uvicorn.error")

# Track if admin has been setup
_admin_setup = False


def _setup_admin(app: FastAPI):
    """Setup SQLAdmin with the initialized engine."""
    global _admin_setup
    if _admin_setup:
        return  # Already setup
    
    authentication_backend = AdminAuthBackend(secret_key="your-secret-key-here")
    authentication_backend.set_app(app)
    admin = Admin(app, postgres_database_session.engine, authentication_backend=authentication_backend)
    
    admin.add_view(UserAdmin)
    admin.add_view(AgentAdmin)
    admin.add_view(ChallengeAdmin)
    admin.add_view(SorryAdmin)
    
    _admin_setup = True


def _create_initial_admin():
    """Create initial admin user from environment variables if specified."""
    admin_email = os.getenv("INITIAL_ADMIN_EMAIL")
    admin_password = os.getenv("INITIAL_ADMIN_PASSWORD")
    
    if not admin_email or not admin_password:
        return
    
    from sorrydb.leaderboard.api.postgres_database_session import get_session
    from sorrydb.leaderboard.database.postgres_database import SQLDatabase
    from sorrydb.leaderboard.model.user import User
    from sorrydb.leaderboard.services.auth_services import hash_password
    
    session = next(get_session())
    db = SQLDatabase(session)
    
    existing_user = db.get_user_by_email(admin_email)
    if not existing_user:
        user = User(
            email=admin_email,
            hashed_password=hash_password(admin_password),
            is_admin=True,
        )
        db.add_user(user)
        logger.info(f"Created initial admin user: {admin_email}")
    elif not existing_user.is_admin:
        existing_user.is_admin = True
        session.commit()
        logger.info(f"Promoted user {admin_email} to admin")
    else:
        logger.info(f"Admin user {admin_email} already exists")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Connecting to database...")
    connect_to_db()
    logger.info("Creating database and tables...")
    create_db_and_tables()
    
    # Setup SQLAdmin after engine is initialized (only in production, not in tests)
    if os.getenv("TESTING") != "true":
        _setup_admin(app)
        _create_initial_admin()

    yield
    logger.info("Application shutting down.")


app = FastAPI(
    lifespan=lifespan,
    license_info={
        "name": "Apache-2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins - restrict this in production
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

# Add session middleware for SQLAdmin authentication
app.add_middleware(SessionMiddleware, secret_key="your-secret-key-here")

app.include_router(auth.router)
app.include_router(challenges.router)
app.include_router(agents.router)
app.include_router(sorries.router)
app.include_router(leaderboard.router)
