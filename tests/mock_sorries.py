from datetime import datetime, timezone

from sorrydb.database.sorry import DebugInfo, Location, Metadata, RepoInfo, Sorry

# initialize some dates to be used throughout tests
JAN_1 = datetime(2023, 1, 1, tzinfo=timezone.utc)
JAN_15 = datetime(2023, 1, 15, tzinfo=timezone.utc)
FEB_1 = datetime(2023, 2, 1, tzinfo=timezone.utc)


# helper functions to create Sorry objects with default values for easier testing
def repo_info_with_defaults() -> RepoInfo:
    return RepoInfo(
        remote="https://github.com/test/repo",
        branch="main",
        commit="abcdef12345",
        lean_version="v4.16.0",
    )


def location_with_defaults() -> Location:
    return Location(
        path="test.lean",
        start_line=1,
        start_column=1,
        end_line=1,
        end_column=6,
    )


def debug_info_with_defaults(goal: str = "test goal", url: str = "") -> DebugInfo:
    return DebugInfo(goal=goal, url=url)


def metadata_with_defaults(
    blame_email_hash: str = "test_hash",
    blame_date: datetime = JAN_1,
    inclusion_date: datetime = JAN_1,
) -> Metadata:
    return Metadata(
        blame_email_hash=blame_email_hash,
        blame_date=blame_date,
        inclusion_date=inclusion_date,
    )


# TODO: This should be useful elsewhere by allowing customization of more Sorry attributes
def sorry_with_defaults(
    goal: str = "test goal",
    inclusion_date=JAN_1,
) -> Sorry:
    return Sorry(
        repo=repo_info_with_defaults(),
        location=location_with_defaults(),
        debug_info=debug_info_with_defaults(goal=goal),
        metadata=metadata_with_defaults(inclusion_date=inclusion_date),
    )
