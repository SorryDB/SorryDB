#!/usr/bin/env python3

import argparse
import logging
import os
import sys

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # Fallback for older Python versions

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
    # --- Step 1: Parse only the config file argument ---
    config_parser = argparse.ArgumentParser(add_help=False)
    config_parser.add_argument(
        "-c",
        "--config-file",
        type=str,
        help="Path to the TOML configuration file.",
        default=None,  # Explicitly default to None
    )
    config_args, _ = config_parser.parse_known_args()

    # --- Step 2: Load configuration from TOML file ---
    config_data = {}
    if config_args.config_file:
        config_path = config_args.config_file
        if os.path.exists(config_path):
            try:
                with open(config_path, "rb") as f:
                    config_data = tomllib.load(f)
            except tomllib.TOMLDecodeError as e:
                print(f"Error parsing config file {config_path}: {e}", file=sys.stderr)
                sys.exit(1)
            except OSError as e:
                print(f"Error reading config file {config_path}: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            # Only warn if the user explicitly provided a non-existent file
            print(
                f"Warning: Config file specified but not found: {config_path}",
                file=sys.stderr,
            )

    # --- Step 3: Create the main parser and common arguments parser ---
    # Common arguments (excluding config_file, handled above)
    common_parser = argparse.ArgumentParser(add_help=False)
    setup_common_arguments(common_parser)  # Add log_level, log_file etc.

    # Set defaults from config file *before* final parsing
    # CLI args will override these if provided
    common_defaults = {
        "log_level": config_data.get("log_level", "INFO").upper(),
        "log_file": config_data.get("log_file", None),
        # Add other common args loaded from config here
    }
    common_parser.set_defaults(**common_defaults)

    # Main parser
    parser = argparse.ArgumentParser(
        description="SorryDB command-line interface.",
        # Inherit common arguments for the main help message if no subcommand is given
        parents=[config_parser, common_parser],
    )

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
