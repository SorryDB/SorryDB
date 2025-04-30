#!/usr/bin/env python3

import argparse
from abc import ABC, abstractmethod
from typing import ClassVar


class Subcommand(ABC):
    """Abstract base class for CLI subcommands."""

    COMMAND: ClassVar[str]  # The name of the subcommand (e.g., "init")
    HELP: ClassVar[str]  # Help text for the subcommand

    @abstractmethod
    def register_args(self, parser: argparse.ArgumentParser) -> None:
        """Add command-specific arguments to the parser."""
        pass

    @abstractmethod
    def run(self, args: argparse.Namespace) -> int:
        """Execute the command's logic."""
        pass
