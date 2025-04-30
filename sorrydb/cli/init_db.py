#!/usr/bin/env python3

import argparse
import datetime
import json
import logging
from pathlib import Path
from typing import Any

from sorrydb.cli.base_command import Subcommand
from sorrydb.database.build_database import init_database


class InitCommand(Subcommand):
    """Handles the initialization of a SorryDB database."""

    COMMAND = "init"
    HELP = "Initialize a SorryDB database from repositories."

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        """Add arguments for the init subcommand."""
        parser.add_argument(
            "--repos-file",
            type=str,
            required=True,
            help="JSON file containing list of repositories to process",
        )
        parser.add_argument(
            "--database-file",
            type=str,
            required=True,
            help="Output file path for the database",
        )
        parser.add_argument(
            "--starting-date",
            type=str,
            default=None,
            help="Starting date for all repositories (format: YYYY-MM-DD) (default: today)",
        )

    def run(self, args: argparse.Namespace) -> int:
        """Execute the init database logic."""
        logger = logging.getLogger(__name__)

        # Parse the starting date if provided
        if args.starting_date:
            try:
                # Parse as YYYY-MM-DD format and make timezone-aware (UTC)
                starting_date = datetime.datetime.strptime(
                    args.starting_date, "%Y-%m-%d"
                )
                starting_date = starting_date.replace(tzinfo=datetime.timezone.utc)
                logger.info(f"Using starting date: {starting_date.isoformat()}")
            except ValueError:
                logger.error(
                    f"Invalid date format: {args.starting_date}. Use YYYY-MM-DD format."
                )
                return 1
        else:
            # Use current date and time if not provided (with UTC timezone)
            starting_date = datetime.datetime.now(datetime.timezone.utc)
            logger.info(
                f"No starting date provided, using current date and time: {starting_date.isoformat()}"
            )

        try:
            with open(args.repos_file, "r") as f:
                repos_data = json.load(f)
        except FileNotFoundError:
            logger.error(f"Repositories file not found: {args.repos_file}")
            return 1
        except json.JSONDecodeError:
            logger.error(
                f"Error decoding JSON from repositories file: {args.repos_file}"
            )
            return 1

        repos_list = [repo["remote"] for repo in repos_data.get("repos", [])]
        if not repos_list:
            logger.error(f"No repositories found in {args.repos_file}")
            return 1

        database_path = Path(args.database_file)

        try:
            init_database(
                repo_list=repos_list,
                starting_date=starting_date,
                database_file=database_path,
            )
            logger.info(f"Database initialized successfully at {database_path}")
            return 0
        except Exception as e:
            logger.error(f"Error building database: {e}")
            logger.exception(e)
            return 1
