#!/usr/bin/env python3

import argparse
import logging
import sys
from typing import Any

from sorrydb.cli.base_command import Subcommand
from sorrydb.cli.deduplicate_db import DeduplicateCommand  # Import the new command
from sorrydb.cli.init_db import InitCommand
from sorrydb.cli.update_db import UpdateCommand

# Subcommand classes registered here will be automatically included in the CLI
SUBCOMMAND_CLASSES: list[type[Subcommand]] = [
    InitCommand,
    UpdateCommand,
    DeduplicateCommand,
]


def setup_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Add common arguments like logging to the parser."""
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


def main() -> None:
    # Create a parent parser for common arguments
    # add_help=False prevents duplicate help messages
    common_parser = argparse.ArgumentParser(add_help=False)
    setup_common_arguments(common_parser)

    parser = argparse.ArgumentParser(description="SorryDB command-line interface.")

    subparsers = parser.add_subparsers(
        dest="command", help="Available commands", required=True
    )

    # Register subcommands by iterating through the classes
    for cmd_class in SUBCOMMAND_CLASSES:
        instance = cmd_class()
        subparser = subparsers.add_parser(
            instance.COMMAND, help=instance.HELP, parents=[common_parser]
        )
        instance.register_args(subparser)
        subparser.set_defaults(func=instance.run)

    args = parser.parse_args()

    # Configure logging based on common arguments
    log_kwargs = {
        "level": getattr(logging, args.log_level),
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    }
    if args.log_file:
        log_kwargs["filename"] = args.log_file
    logging.basicConfig(**log_kwargs)

    # Execute the run method associated with the chosen subcommand
    # The 'func' attribute now holds the 'run' method of the command instance
    return_code: int = args.func(args)  # Add type hint for return_code
    sys.exit(return_code)


if __name__ == "__main__":
    main()
