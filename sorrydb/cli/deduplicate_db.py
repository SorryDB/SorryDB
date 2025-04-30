#!/usr/bin/env python3

import argparse
import logging
from pathlib import Path

from sorrydb.cli.base_command import Subcommand  # Import base class
from sorrydb.database.deduplicate_database import deduplicate_database


class DeduplicateCommand(Subcommand):
    """Handles deduplicating sorries within a SorryDB database."""

    COMMAND = "deduplicate"
    HELP = "Deduplicate the sorries in a SorryDB database."

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        """Add arguments for the deduplicate subcommand."""
        parser.add_argument(
            "--database-file",
            type=str,
            required=True,
            help="Path to the database JSON file",
        )
        # Common args --log-level and --log-file are handled by the parent parser
        parser.add_argument(
            "--results-file",
            type=str,
            default=None,
            help="Path to write query results (JSON format). If not provided query results are sent to stdout",
        )

    def run(self, args: argparse.Namespace) -> int:
        """Execute the deduplicate database logic."""
        logger = logging.getLogger(__name__)

        # Convert file names arguments to Path
        database_path = Path(args.database_file)
        query_results_path = Path(args.results_file) if args.results_file else None

        if not database_path.exists():
            logger.error(f"Database file not found: {database_path}")
            return 1

        try:
            deduplicate_database(
                database_path=database_path, query_results_path=query_results_path
            )
            return 0
        except Exception as e:
            logger.error(f"Error deduplicating database: {e}")
            logger.exception(e)
            return 1
