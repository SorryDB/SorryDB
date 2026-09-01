#!/usr/bin/env python3

import argparse
import logging
from datetime import datetime, timezone

from sorrydb.database.github_index import index_github


def main():
    parser = argparse.ArgumentParser(
        description="Index Lean repositories directly from the GitHub API. "
        "Stand-in for the Reservoir index while "
        "https://github.com/leanprover/reservoir/issues/109 is open. "
        "Requires GITHUB_TOKEN or GH_TOKEN to be set."
    )
    parser.add_argument(
        "--updated-since",
        required=True,
        help="Only include repos updated since this date (isoformat, e.g. YYYY-MM-DD)",
    )
    parser.add_argument(
        "--minimum-stars",
        type=int,
        required=True,
        help="Minimum number of GitHub stars",
    )
    parser.add_argument("--output", required=True, help="Output JSON file path")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    # Parse the date and make it timezone-aware (UTC)
    updated_since = datetime.fromisoformat(args.updated_since).replace(
        tzinfo=timezone.utc
    )

    try:
        index_github(updated_since, args.minimum_stars, args.output)
    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    main()
