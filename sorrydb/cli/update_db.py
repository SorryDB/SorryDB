#!/usr/bin/env python3

import argparse
import logging
from pathlib import Path
from typing import Any

from sorrydb.cli.base_command import Subcommand
from sorrydb.database.build_database import update_database


class UpdateCommand(Subcommand):
    """Handles updating an existing SorryDB database."""

    COMMAND = "update"
    HELP = "Update an existing SorryDB database."

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        """Add arguments for the update subcommand."""
        parser.add_argument(
            "--database-file",
            type=str,
            required=True,
            help="Path to the database JSON file",
        )
        parser.add_argument(
            "--lean-data",
            type=str,
            default=None,
            help="Directory to store Lean data (default: use temporary directory)",
        )
        parser.add_argument(
            "--stats-file",
            type=str,
            default=None,
            help="Path to write update statistics (JSON format)",
        )

    def run(self, args: argparse.Namespace) -> int:
        """Execute the update database logic."""
        logger = logging.getLogger(__name__)

        # Convert file names arguments to Path
        lean_data = Path(args.lean_data) if args.lean_data else None
        database_path = Path(args.database_file)
        stats_file_path = Path(args.stats_file) if args.stats_file else None

        if not database_path.exists():
            logger.error(f"Database file not found: {database_path}")
            return 1

        try:
            update_database(
                database_path=database_path,
                lean_data=lean_data,
                stats_file=stats_file_path,
            )
            logger.info(f"Database updated successfully: {database_path}")
            return 0
        except Exception as e:
            logger.error(f"Error updating database: {e}")
            logger.exception(e)
            return 1
