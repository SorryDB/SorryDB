import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class RepoInfo:
    remote: str  # URL of the remote repository
    branch: str  # Branch name where the sorry was found
    commit: str  # Commit hash where the sorry was found
    lean_version: str  # Version of Lean used on the commit where the sorry was found


@dataclass
class Location:
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    file: str  # File path where the sorry was found


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
    
    @staticmethod
    def default_json_serialization(obj):
        if isinstance(obj, datetime):
            obj.isoformat() 
        else:
            str(obj)

    def __post_init__(self):
        if self.id is None:
            hash_dict = asdict(self)

            # Remove fields we don't want to include in the hash
            hash_dict.pop("id", None)
            # TODO: remove inclusion date

            # Convert to a stable string representation and hash it
            hash_str = json.dumps(hash_dict, sort_keys=True, default=Sorry.default_json_serialization)
            self.id = hashlib.sha256(hash_str.encode()).hexdigest()

    def _serialize_datetimes(self, data):
        """Recursively convert datetime objects to ISO format strings for JSON serialization."""
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, datetime):
                    data[key] = value.isoformat()
                elif isinstance(value, (dict, list)):
                    self._serialize_datetimes(value)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, datetime):
                    data[i] = item.isoformat()
                elif isinstance(item, (dict, list)):
                    self._serialize_datetimes(item)
