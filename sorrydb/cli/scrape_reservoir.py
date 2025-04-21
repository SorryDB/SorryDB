#!/usr/bin/env python3

import argparse
import datetime
from datetime import datetime, timezone

from sorrydb.database.reservoir import scrape_reservoir


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Lean repositories from reservoir index"
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

    # Parse the date and make it timezone-aware (UTC)
    updated_since = datetime.fromisoformat(args.updated_since).replace(
        tzinfo=timezone.utc
    )

    try:
        scrape_reservoir(updated_since, args.minimum_stars, args.output)
    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    main()
