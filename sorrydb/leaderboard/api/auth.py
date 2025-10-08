from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.exc import IntegrityError

from sorrydb.leaderboard.api.app_config import get_repository
from sorrydb.leaderboard.api.dependencies import get_current_active_user
from sorrydb.leaderboard.database.postgres_database import SQLDatabase
from sorrydb.leaderboard.model.user import User
from sorrydb.leaderboard.services.auth_services import (
    authenticate_user,
    create_access_token,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    id: str
    email: str
    is_admin: bool
    is_active: bool


class Token(BaseModel):
    access_token: str
    token_type: str


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    user_create: UserCreate,
    db: Annotated[SQLDatabase, Depends(get_repository)],
):
    try:
        user = register_user(db, user_create.email, user_create.password)
        return user
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )


@router.post("/token", response_model=Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[SQLDatabase, Depends(get_repository)],
):
    user = authenticate_user(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserRead)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    return current_user
