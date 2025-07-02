import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, StaticPool, create_engine

from sorrydb.leaderboard.api.app import app
from sorrydb.leaderboard.api.app_config import get_repository
from sorrydb.leaderboard.api.postgres_database_session import get_session


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",  # in-memory SQLite database
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # maintain a single database connection globally
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
