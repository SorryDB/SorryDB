import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, StaticPool, create_engine

from sorrydb.leaderboard.api.app import app, _setup_admin
from sorrydb.leaderboard.api.postgres_database_session import get_session
from sorrydb.leaderboard.api import postgres_database_session


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    
    # Set the test engine globally for SQLAdmin
    postgres_database_session.engine = engine
    
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    
    # Reset admin setup flag to allow re-setup in tests
    import sorrydb.leaderboard.api.app as app_module
    app_module._admin_setup = False
    
    # Setup SQLAdmin with the test engine
    _setup_admin(app)
    
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture(name="test_user")
def test_user_fixture(client: TestClient):
    response = client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": "testpass123"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture(name="test_admin_user")
def test_admin_user_fixture(client: TestClient, session: Session):
    from sorrydb.leaderboard.database.postgres_database import SQLDatabase
    
    response = client.post(
        "/auth/register",
        json={"email": "admin@example.com", "password": "adminpass123"},
    )
    assert response.status_code == 201
    user_data = response.json()
    
    db = SQLDatabase(session)
    user = db.get_user_by_id(user_data["id"])
    user.is_admin = True
    session.add(user)
    session.commit()
    
    return user_data


@pytest.fixture(name="auth_headers")
def auth_headers_fixture(client: TestClient, test_user: dict):
    response = client.post(
        "/auth/token",
        data={"username": "test@example.com", "password": "testpass123"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(name="admin_auth_headers")
def admin_auth_headers_fixture(client: TestClient, test_admin_user: dict):
    response = client.post(
        "/auth/token",
        data={"username": "admin@example.com", "password": "adminpass123"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
