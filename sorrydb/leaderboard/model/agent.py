from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship, SQLModel

# type check without introucing a runtime circular dependency with `Challenge`
if TYPE_CHECKING:
    from .challenge import Challenge


class Agent(SQLModel, table=True):
    id: str | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    challenges: list["Challenge"] = Relationship(back_populates="agent")
