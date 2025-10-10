from typing import TYPE_CHECKING, Optional
import uuid
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .challenge import Challenge
    from .user import User


class Agent(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str = Field(index=True)
    user_id: str = Field(foreign_key="user.id")
    
    challenges: list["Challenge"] = Relationship(back_populates="agent")
    user: Optional["User"] = Relationship(back_populates="agents")
    
    def __str__(self) -> str:
        return self.name
