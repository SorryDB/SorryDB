import datetime
from enum import Enum

from sorrydb.database.sorry import Sorry


class ChallengeStatus(str, Enum):
    AWAITING_SUBMISSION = "AWAITING_SUBMISSION"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    FAILED = "FAILED"
    SUCCESS = "SUCCESS"


class Challenge:
    id: str
    agent_id: str
    deadline: datetime
    sorry: Sorry
    status: ChallengeStatus = ChallengeStatus.AWAITING_SUBMISSION
