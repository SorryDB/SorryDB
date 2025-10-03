import json
import os
import re
import ssl
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

from langchain_core.tools import tool
import logging
import sys


def setup_logger(name: str = None, level: str = "INFO") -> logging.Logger:
    """
    Set up a logger with rich formatting that shows file, line, and function.

    Args:
        name: Logger name (defaults to root logger)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers:
        # Create console handler
        handler = logging.StreamHandler(sys.stdout)

        # Create formatter with file, function, and line info
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d - %(funcName)s()] - %(message)s",  # noqa: E501
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Set formatter
        handler.setFormatter(formatter)

        # Add handler to logger
        logger.addHandler(handler)

        # Set level
        logger.setLevel(getattr(logging, level.upper()))

    return logger


def get_logger(name: str = None) -> logging.Logger:
    """
    Get or create a logger with the standard configuration.

    Args:
        name: Logger name (typically __name__ from the calling module)

    Returns:
        Configured logger instance
    """
    if name is None:
        # Get the caller's module name
        import inspect

        frame = inspect.stack()[1]
        module = inspect.getmodule(frame[0])
        name = module.__name__ if module else "ax_agent"

    return setup_logger(name)


logger = get_logger(__name__)


def format_lean_errors(error_output: str, file_path: str, file_content: str) -> str:
    """Format Lean compiler errors with code context (only for errors, not warnings)."""
    lines = file_content.splitlines()
    pattern = re.compile(rf"{re.escape(str(file_path))}:(\d+):(\d+):\s*(.*)")
    formatted = []

    for error_line in error_output.splitlines():
        match = pattern.match(error_line)
        if match:
            line_num = int(match.group(1))
            col_num = int(match.group(2))
            msg = match.group(3)

            # Only format errors, not warnings
            if "error:" in msg.lower():
                if 0 < line_num <= len(lines):
                    code = lines[line_num - 1]
                    marker = " " * (col_num - 1) + "^^^"

                    formatted.extend(
                        [
                            f"\n╭─ Error at line {line_num}:{col_num}",
                            f"│  {code}",
                            f"│  {marker}",
                            f"╰─ {msg}",
                        ]
                    )
                    continue

        formatted.append(error_line)

    return "\n".join(formatted)


def trim_warnings(output: str) -> str:
    """Remove warning lines from Lean compiler output.

    Filters out common warnings like:
    - declaration uses 'sorry'
    - unused variables
    - other warning messages

    Args:
        output: Raw Lean compiler output

    Returns:
        Output with warning lines removed
    """
    filtered_lines = []
    for line in output.splitlines():
        # Skip lines containing common warnings
        if any(
            warning in line.lower()
            for warning in [
                "warning:",
                "declaration uses 'sorry'",
                "uses sorry",
                "unused variable",
                "unused parameter",
            ]
        ):
            continue
        filtered_lines.append(line)

    return "\n".join(filtered_lines)


def read_file(base_folder: str, file_path: str) -> str:
    """Read a file's content.

    Args:
        base_folder: Base folder path
        file_path: Path to file relative to base_folder

    Returns:
        File content or directory listing if path is a directory
    """
    try:
        full_path = Path(base_folder) / file_path
        if not full_path.exists():
            return ""

        # Check if it's a directory
        if full_path.is_dir():
            files = sorted([f.name for f in full_path.iterdir()])
            return f"[Directory: {file_path}]\nContents:\n" + "\n".join(
                f"  - {f}" for f in files
            )

        return full_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return f"Error reading file: {e}"
