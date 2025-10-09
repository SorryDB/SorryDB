from typing import TYPE_CHECKING, Optional
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .challenge import Challenge
    from .user import User


class Agent(SQLModel, table=True):
    id: str | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    user_id: str = Field(foreign_key="user.id")
    
    challenges: list["Challenge"] = Relationship(back_populates="agent")
    user: Optional["User"] = Relationship(back_populates="agents")
