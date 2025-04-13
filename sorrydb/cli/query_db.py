#!/usr/bin/env python3

import argparse
import logging
from pathlib import Path

from sorrydb.database.query_database import query_database


def main():
    parser = argparse.ArgumentParser(description="Query a SorryDB database.")
    parser.add_argument(
        "--database-file",
        type=str,
        required=True,
        help="Path to the database JSON file",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)",
    )
    parser.add_argument(
        "--log-file", type=str, help="Log file path (default: output to stdout)"
    )
    parser.add_argument(
        "--results-file",
        type=str,
        default=None,
        help="Path to write query results (JSON format). If not provided query results are sent to stdout",
    )

    args = parser.parse_args()

    # Configure logging
    log_kwargs = {
        "level": getattr(logging, args.log_level),
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    }
    if args.log_file:
        log_kwargs["filename"] = args.log_file
    logging.basicConfig(**log_kwargs)

    logger = logging.getLogger(__name__)

    # Convert file names arguments to Path
    database_path = Path(args.database_file)
    query_results_path = Path(args.results_file) if args.results_file else None

    try:
        query_database(
            database_path=database_path, query_results_path=query_results_path
        )
        return 0

    except Exception as e:
        logger.error(f"Error querying database: {e}")
        logger.exception(e)
        return 1


if __name__ == "__main__":
    exit(main())
