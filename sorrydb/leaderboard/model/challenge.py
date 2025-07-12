import enum
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Column, Enum, Field, Relationship, SQLModel

from sorrydb.leaderboard.model.agent import Agent
from sorrydb.leaderboard.model.sorry import SQLSorry


class ChallengeStatus(str, enum.Enum):
    AWAITING_SUBMISSION = "AWAITING_SUBMISSION"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    FAILED = "FAILED"
    SUCCESS = "SUCCESS"


class Challenge(SQLModel, table=True):
    # TODO: We can use the `uuid` library or have the database generate this automatically
    # Link to UUID for SQLModel: https://sqlmodel.tiangolo.com/advanced/uuid/#models-with-uuids
    id: Optional[str] = Field(
        default_factory=lambda: str(uuid.uuid4()), primary_key=True
    )
    deadline: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=1)
    )
    status: ChallengeStatus = Field(
        default=ChallengeStatus.AWAITING_SUBMISSION,
        sa_column=Column(Enum(ChallengeStatus)),
    )
    # TODO: we might want challenge submission to be a different domain object
    submission: Optional[str] = Field(default=None)

    sorry_id: Optional[str] = Field(default=None, foreign_key="sqlsorry.id")
    sorry: Optional[SQLSorry] = Relationship(back_populates="challenges")

    agent_id: Optional[str] = Field(default=None, foreign_key="agent.id")
    agent: Optional[Agent] = Relationship(back_populates="challenges")
