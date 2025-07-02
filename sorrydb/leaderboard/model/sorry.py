from datetime import datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel

from sorrydb.database.sorry import Sorry


class SQLSorry(SQLModel, table=True):
    id: Optional[str] = Field(primary_key=True)

    remote: str = Field()
    branch: str = Field()
    commit: str = Field()
    lean_version: str = Field()

    path: str = Field()
    start_line: int = Field()
    start_column: int = Field()
    end_line: int = Field()
    end_column: int = Field()

    goal: str = Field()
    url: str = Field()

    blame_email_hash: str = Field()
    blame_date: datetime = Field()
    inclusion_date: datetime = Field()

    challenges: list["Challenge"] = Relationship(back_populates="sorry")

    @staticmethod
    def from_json_sorry(json_sorry: Sorry) -> "SQLSorry":
        return SQLSorry(
            id=json_sorry.id,
            remote=json_sorry.repo.remote,
            branch=json_sorry.repo.branch,
            commit=json_sorry.repo.commit,
            lean_version=json_sorry.repo.lean_version,
            path=json_sorry.location.path,
            start_line=json_sorry.location.start_line,
            start_column=json_sorry.location.start_column,
            end_line=json_sorry.location.end_line,
            end_column=json_sorry.location.end_column,
            goal=json_sorry.debug_info.goal,
            url=json_sorry.debug_info.url,
            blame_email_hash=json_sorry.metadata.blame_email_hash,
            blame_date=json_sorry.metadata.blame_date,
            inclusion_date=json_sorry.metadata.inclusion_date,
        )
