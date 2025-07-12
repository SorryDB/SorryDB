import json
from collections import defaultdict
from itertools import islice, zip_longest
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


def varied_repo_frequent_n_sorries(sorries: list[Sorry], n: int) -> list[Sorry]:
    """
    Takes `n` sorries from a list, while varying the source repo and favoring recent blame dates.

    This is used to generate an interesting static benchmark at a given point.
    """
    # Group sorries by repository
    repo_groups = defaultdict(list)
    for sorry in sorries:
        repo_groups[sorry.repo.remote].append(sorry)

    # Sort each repository group by blame_date (most recent first)
    for repo, repo_sorries in repo_groups.items():
        repo_groups[repo] = sorted(
            repo_sorries, key=lambda s: s.metadata.blame_date, reverse=True
        )

    # Create a generator for interleaved sorries from different repos
    interleaved_sorries_generator = (
        # Use zip_longest to create tuples of sorries from each repo position
        sorry
        for sorries_tuple in zip_longest(*repo_groups.values())
        # and flatten the result while filtering out None values
        for sorry in sorries_tuple
        if sorry is not None
    )

    # Use islice to take only the first n elements from the generator
    return list(islice(interleaved_sorries_generator, n))


def deduplicate_database(
    database_path: Path,
    query_results_path: Optional[Path] = None,
    max_sorries: Optional[int] = None,
):
    """
    Deduplicate the database and write the results to `query_results_path`.
    If no path is provided, write the results to stdout.
    """
    database = JsonDatabase()

    database.load_database(database_path)

    deduplicated_sorries = deduplicate_sorries_by_goal(database.get_sorries())

    if max_sorries:
        deduplicated_sorries = varied_repo_frequent_n_sorries(
            deduplicated_sorries, max_sorries
        )

    database_format_deduplicated_sorries = {
        "documentation": "deduplicated list of sorries, for each unique goal string the most recent inclusion date is chosen",
        "sorries": deduplicated_sorries,
    }
    if query_results_path:
        with open(query_results_path, "w") as f:
            json.dump(
                database_format_deduplicated_sorries,
                f,
                indent=2,
                cls=SorryJSONEncoder,
            )
    else:
        json_string = json.dumps(
            database_format_deduplicated_sorries,
            indent=2,
            cls=SorryJSONEncoder,
        )
        print(json_string)
    return database_format_deduplicated_sorries
