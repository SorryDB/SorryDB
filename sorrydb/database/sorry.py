import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class RepoInfo:
    remote: str
    branch: str
    commit: str
    lean_version: str  # Version of Lean used on the commit where the sorry was found


@dataclass
class Location:
    path: str  # File path where the sorry was found
    start_line: int
    start_column: int
    end_line: int
    end_column: int


@dataclass
class DebugInfo:
    goal: str  # The goal state at the sorry
    url: str  # URL to the sorry in the repository


@dataclass
class Metadata:
    blame_email_hash: str  # Hash of the email of the person who added the sorry
    blame_date: datetime  # Date when the sorry was added
    inclusion_date: datetime  # Date when the sorry was included in the database


@dataclass
class Sorry:
    repo: RepoInfo
    location: Location
    debug_info: DebugInfo
    metadata: Metadata
    id: Optional[str] = field(
        default=None, init=False
    )  # Unique identifier for the sorry

    @classmethod
    def from_dict(cls, data: dict) -> "Sorry":
        """Create a Sorry object from a dictionary."""

        # Helper function to convert string dates to datetime objects
        def parse_date(date_str):
            # Some dictionaries may have already parsed the date string into a datetime
            return (
                datetime.fromisoformat(date_str)
                if isinstance(date_str, str)
                else date_str
            )

        metadata = data["metadata"]

        sorry = cls(
            repo=RepoInfo(**data["repo"]),
            location=Location(**data["location"]),
            debug_info=DebugInfo(**data["debug_info"]),
            metadata=Metadata(
                blame_email_hash=metadata["blame_email_hash"],
                blame_date=parse_date(metadata["blame_date"]),
                inclusion_date=parse_date(metadata["inclusion_date"]),
            ),
        )

        # Set id after because it is not allowed in constructor
        sorry.id = data.get("id")

        return sorry

    def __post_init__(self):
        if self.id is None:
            hash_dict = asdict(self)

            # Remove fields we don't want to include in the hash
            hash_dict.pop("id", None)
            hash_dict["metadata"].pop("inclusion_date")

            # Convert to a stable string representation so that Sorry ids are consistent across database runs
            hash_str = json.dumps(hash_dict, sort_keys=True, cls=SorryJSONEncoder)
            self.id = hashlib.sha256(hash_str.encode()).hexdigest()


class SorryJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for Sorry objects."""

    def default(self, obj):
        if isinstance(obj, Sorry):
            return asdict(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def sorry_object_hook(d):
    """Object hook for JSON deserialization that converts dicts to Sorry objects."""
    if all(key in d for key in ["repo", "location", "debug_info", "metadata", "id"]):
        return Sorry.from_dict(d)
    return d
