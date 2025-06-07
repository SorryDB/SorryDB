import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

from sorrydb.database.sorry import Sorry, SorryJSONEncoder
from sorrydb.database.sorry_database import JsonDatabase


def deduplicate_sorries_by_goal(sorries: list[Sorry]):
    """
    Deduplicate a list of sorries by goal.
    If sorries share a goal, prefer the sorry with the most recent inclusion date.
    """

    # Group sorries by goal
    goal_groups = defaultdict(list)
    for sorry in sorries:
        goal_groups[sorry.debug_info.goal].append(sorry)

    return [
        # find sorry with most recent (max) inclusion_date
        max(group, key=lambda s: s.metadata.inclusion_date)
        for group in goal_groups.values()
    ]


def deduplicate_database(
    database_path: Path,
    query_results_path: Optional[Path] = None,
):
    """
    Deduplicate the database and write the results to `query_results_path`.
    If no path is provided, write the results to stdout.
    """
    database = JsonDatabase()

    database.load_database(database_path)

    deduplicated_sorries = {
        "documentation": "deduplicated list of sorries, for each unique goal string the most recent inclusion date is chosen",
        "sorries": deduplicate_sorries_by_goal(database.get_sorries())
    }
    if query_results_path:
        with open(query_results_path, "w") as f:
            json.dump(
                deduplicated_sorries,
                f,
                indent=2,
                cls=SorryJSONEncoder,
            )
    else:
        json_string = json.dumps(
            deduplicated_sorries,
            indent=2,
            cls=SorryJSONEncoder,
        )
        print(json_string)

    return deduplicated_sorries
