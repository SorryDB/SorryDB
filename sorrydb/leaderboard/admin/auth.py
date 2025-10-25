from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import Response


from starlette import status as http_status

from sorrydb.leaderboard.database.postgres_database import SQLDatabase
from sorrydb.leaderboard.services.auth_services import (
    authenticate_user,
    create_access_token,
    decode_access_token,
)


class AdminAuthBackend(AuthenticationBackend):
    def __init__(self, secret_key: str):
        super().__init__(secret_key)
        self._app = None
    
    def set_app(self, app):
        """Store reference to the FastAPI app for dependency resolution."""
        self._app = app
    
    def _get_session(self):
        """Get session respecting FastAPI dependency overrides."""
        from sorrydb.leaderboard.api.postgres_database_session import get_session
        
        # Check if there's an override (used in tests)
        if self._app and hasattr(self._app, 'dependency_overrides'):
            override = self._app.dependency_overrides.get(get_session)
            if override:
                return override()
        
        # Use the normal get_session
        session_gen = get_session()
        return next(session_gen)
    
    async def login(self, request: Request) -> bool:
        """Handle login form submission."""
        form = await request.form()
        username = form.get("username")
        password = form.get("password")

        session = self._get_session()
        db = SQLDatabase(session)
        
        user = authenticate_user(username, password, db)
        if user and user.is_admin:
            token = create_access_token(data={"sub": user.id})
            request.session.update({"token": token})
            return True

        return False

    async def logout(self, request: Request) -> bool:
        """Handle logout."""
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> Response | bool:
        """Check if user is authenticated and is admin."""
        # First check session token (for web UI)
        token = request.session.get("token")
        
        # If no session token, check Authorization header (for API/tests)
        if not token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.replace("Bearer ", "")
        
        if not token:
            # For requests without any auth (no session, no header), return 401
            # This handles both unauthenticated API calls and browser requests
            return Response(content="Unauthorized", status_code=http_status.HTTP_401_UNAUTHORIZED)

        payload = decode_access_token(token)
        if payload is None:
            return Response(content="Unauthorized", status_code=http_status.HTTP_401_UNAUTHORIZED)

        user_id = payload.get("sub")
        if not user_id:
            return Response(content="Unauthorized", status_code=http_status.HTTP_401_UNAUTHORIZED)

        session = self._get_session()
        db = SQLDatabase(session)
        user = db.get_user_by_id(user_id)
        
        if user is None:
            return Response(content="Unauthorized", status_code=http_status.HTTP_401_UNAUTHORIZED)
        
        if not user.is_admin:
            return Response(content="Forbidden", status_code=http_status.HTTP_403_FORBIDDEN)
        
        return True
