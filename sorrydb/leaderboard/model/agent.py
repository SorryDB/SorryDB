from sqlmodel import Field, Relationship, SQLModel


class Agent(SQLModel, table=True):
    id: str | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    challenges: list["Challenge"] = Relationship(back_populates="agent")
