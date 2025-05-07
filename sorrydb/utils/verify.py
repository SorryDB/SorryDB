#!/usr/bin/env python3

import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from .repl_ops import LeanRepl, setup_repl
from sorrydb.database.sorry import Location

logger = logging.getLogger(__name__)


def verify_proof(repo_dir: Path, lean_version: str, location: Location, proof: str) -> bool:
    """
    Verify if a proof successfully replaces a sorry at a specific location.

    Args:
        repo_dir: Path to the repository
        lean_version: Lean version tag
        location: Location object containing sorry location info (path and coordinates)
        proof: The proof string to replace the sorry

    Returns:
        Boolean indicating whether the proof successfully replaces the sorry
    """
    # Load the original file
    file_path = location.path
    full_path = repo_dir / Path(file_path)
    original_file = full_path.read_text()

    # Obtain absolute linear character indices of sorry
    start_index = position_to_index(
        original_file, location.start_line, location.start_column
    )
    end_index = position_to_index(
        original_file, location.end_line, location.end_column
    )

    # Replace sorry with proof
    modified_file = original_file[:start_index] + proof + original_file[end_index:]
    offset = start_index - end_index + len(proof)

    # Create a temporary file in the same directory as the original file
    parent_dir = full_path.parent
    with tempfile.NamedTemporaryFile(
        suffix=".lean", dir=parent_dir, delete=True
    ) as tmp:
        tmp.write(modified_file.encode("utf-8"))
        tmp.flush()  # Ensure all data is written to disk

        # Get the relative path from repo_dir to the temp file
        temp_path = Path(tmp.name)
        modified_file_path = temp_path.relative_to(repo_dir)

        # Read sorries from original file
        repl_binary = setup_repl(repo_dir, lean_version)
        with LeanRepl(repo_dir, repl_binary) as repl:
            try:
                sorries = repl.read_file(file_path)
            except RuntimeError as e:
                logger.warning(f"Failed to analyze original file: {e}")
                return False
        with LeanRepl(repo_dir, repl_binary) as repl:
            try:
                modified_sorries = repl.read_file(modified_file_path)
            except RuntimeError as e:
                logger.warning(f"Failed to analyze modified file: {e}")
                return False

        # first check if we have removed one sorry
        if len(sorries) != len(modified_sorries) + 1:
            logger.info("Expected one less sorry in modified file")
            return False

        # Add character index to each sorry
        for sorry in sorries:
            sorry["index"] = position_to_index(
                original_file,
                sorry["location"]["start_line"],
                sorry["location"]["start_column"],
            )

        for sorry in modified_sorries:
            sorry["index"] = position_to_index(
                modified_file,
                sorry["location"]["start_line"],
                sorry["location"]["start_column"],
            )

        # next check if the sorries match up
        for original_sorry in sorries:
            # Skip the sorry that was replaced
            if original_sorry["index"] == start_index:
                continue

            # Find corresponding sorry in modified file
            expected_index = original_sorry["index"]
            if original_sorry["index"] > start_index:
                expected_index += offset

            # Look for matching sorry in modified file
            match_found = False
            for modified_sorry in modified_sorries:
                if modified_sorry["index"] == expected_index:
                    # check if goals match
                    if original_sorry["goal"] != modified_sorry["goal"]:
                        logger.info("Matching sorry index, but goals do not agree")
                        return False
                    else:
                        match_found = True
                        break
            if not match_found:
                logger.info("Sorries do not match up")
                return False

        logger.info("Proof verified")
        return True


def position_to_index(content: str, line: int, column: int) -> int:
    """
    Convert a (line, column) position to a linear character index.

    Args:
        content: File content as a string
        line: Line number (starts at 1)
        column: Column number

    Returns:
        Linear character index corresponding to the position

    Raises:
        ValueError: If the line or column is out of range
    """
    lines = content.split("\n")

    # Check if coordinates are valid
    if line < 1 or line > len(lines):
        raise ValueError(f"Line {line} out of range (1-{len(lines)})")
    if column < 0 or column > len(lines[line - 1]):
        raise ValueError(f"Column {column} is out of range for line {line}")

    # Add up the lengths of all previous lines plus newline characters
    index = sum(len(lines[i]) + 1 for i in range(line - 1))

    return index + column
