#!/usr/bin/env python3

import argparse
import logging

from sorrydb.database.github_index import index_github


def main():
    parser = argparse.ArgumentParser(
        description="Index Lean repositories directly from the GitHub API. "
        "Stand-in for the Reservoir index while "
        "https://github.com/leanprover/reservoir/issues/109 is open. "
        "Writes the whole universe of repositories meeting the inclusion "
        "criteria, with each one's stars and last activity as data. Activity "
        "eligibility is recomputed by the crawl on every run, from "
        "SORRYDB_MIN_STARS and SORRYDB_ACTIVITY_DAYS, so there is deliberately "
        "no star or recency filter here. "
        "Requires GITHUB_TOKEN or GH_TOKEN to be set."
    )
    parser.add_argument("--output", required=True, help="Output JSON file path")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    try:
        index_github(args.output)
    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    main()
