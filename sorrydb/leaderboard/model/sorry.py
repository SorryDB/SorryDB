import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

from sorrydb.database.sorry import Sorry

# type check without introucing a runtime circular dependency with `Challenge`
if TYPE_CHECKING:
    from .challenge import Challenge


class SQLSorry(SQLModel, table=True):
    id: Optional[str] = Field(primary_key=True)

    remote: str = Field(index=True)
    branch: str = Field()
    commit: str = Field()
    lean_version: str = Field(index=True)

    path: str = Field()
    start_line: int = Field()
    start_column: int = Field()
    end_line: int = Field()
    end_column: int = Field()

    goal: str = Field()
    url: str = Field()

    blame_email_hash: str = Field()
    blame_date: datetime = Field(index=True)
    inclusion_date: datetime = Field(index=True)

    # NULL means "present in the latest crawled dataset". Retirement is a flag
    # and never a delete, because challenge.sorry_id is a foreign key onto this
    # table: a completed challenge has to keep resolving to the exact sorry it
    # was created for, long after that sorry's repo has moved on.
    # Not indexed: almost every row is NULL, so an index would not narrow much.
    retired_at: Optional[datetime] = Field(default=None)

    challenges: list["Challenge"] = Relationship(back_populates="sorry")
    
    def __str__(self) -> str:
        filename = self.path.split("/")[-1] if self.path else "Unknown"
        return f"{filename}:{self.start_line}"

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


class SorrySortField(str, enum.Enum):
    """Columns the sorry list can be sorted on."""

    inclusion_date = "inclusion_date"
    blame_date = "blame_date"


class SortOrder(str, enum.Enum):
    asc = "asc"
    desc = "desc"
