import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from sorrydb.database.sorry import Sorry


class ChallengeStatus(str, Enum):
    AWAITING_SUBMISSION = "AWAITING_SUBMISSION"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    FAILED = "FAILED"
    SUCCESS = "SUCCESS"


# TODO: The Challenge object is complex enough that it probably shouldn't be a dataclass.
# For now the field initiatlizers provide a short cut to getting a working object.
@dataclass
class Challenge:
    agent_id: str
    sorry: Sorry
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    deadline: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=1)
    )
    status: ChallengeStatus = ChallengeStatus.AWAITING_SUBMISSION
    # TODO: we might want challenge submission to be a different domain object
    submission: Optional[str] = None
