#!/usr/bin/env python3

import logging
import tempfile
from pathlib import Path

from lean_interact import FileCommand, LeanREPLConfig, LeanServer, LocalProject
from lean_interact.interface import LeanError
from sorrydb.database.sorry import Location

from .repl_ops import check_lean_file

logger = logging.getLogger(__name__)

REPL_TIMEOUT = 60


def verify_lean_interact(
    repo_dir: Path,
    location: Location,
    proof: str,
    timeout: float = REPL_TIMEOUT,
) -> tuple[bool, str]:
    """
    Verify if a proof successfully replaces a sorry at a specific location using LeanInteract.

    This method uses the LeanInteract library to analyze Lean files and verify proofs.
    It creates a temporary file with the proof substituted for the sorry, then checks
    that the proof is valid by ensuring:
    1. The modified file can be built
    2. Exactly one sorry has been removed
    3. All other sorries remain in the same positions with the same goals

    Args:
        repo_dir: Path to the repository
        location: Location object containing sorry location info (path and coordinates)
        proof: The proof string to replace the sorry
        timeout: Timeout in seconds for REPL operations (default: REPL_TIMEOUT)

    Returns:
        Tuple of (is_valid, error_message) where:
        - is_valid: Boolean indicating whether the proof successfully replaces the sorry
        - error_message: Empty string if valid, otherwise contains the error description
    """
    logger.info("Using LEAN INTERACT verify")
    # Load the original file
    file_path = location.path
    full_path = repo_dir / Path(file_path)
    original_file = full_path.read_text()

    # Obtain absolute linear character indices of sorry
    start_index = position_to_index(
        original_file, location.start_line, location.start_column
    )
    end_index = position_to_index(original_file, location.end_line, location.end_column)

    # Replace sorry with proof
    modified_file = original_file[:start_index] + proof + original_file[end_index:]
    offset = start_index - end_index + len(proof)

    # Create a temporary file in the same directory as the original file
    parent_dir = full_path.parent
    with tempfile.NamedTemporaryFile(
        suffix=".lean", dir=parent_dir, delete=True
    ) as tmp:
        logger.debug(f"Writing modified file for LeanInteract to check: {modified_file}")
        tmp.write(modified_file.encode("utf-8"))
        tmp.flush()  # Ensure all data is written to disk

        # Get the relative path from repo_dir to the temp file
        temp_path = Path(tmp.name).resolve()
        # repo_dir must be resolved if it is a relative path
        modified_file_path = temp_path.relative_to(repo_dir.resolve())

        # Quickly verify the file with lake env lean before doing full analysis
        logger.info("Checking file")
        can_build, errors = check_lean_file(
            repo_dir, modified_file_path, show_warnings=False
        )
        if not can_build:
            error_msg = f"Cannot build modified file: {errors}\n"
            logger.info(f"Cannot build modified file {errors}")
            return False, error_msg

        # Use LeanInteract to analyze files
        # Note: LocalProject automatically infers the Lean version from the project
        logger.info("Building REPL config")
        project = LocalProject(directory=str(repo_dir.resolve()))
        config = LeanREPLConfig(
            project=project,
            verbose=False,
        )

        try:
            logger.info("Creating Lean server")
            server = LeanServer(config)

            # Read sorries from original file
            try:
                logger.info(f"Reading original file with timeout {timeout}")
                original_response = server.run(
                    FileCommand(path=str(file_path)), timeout=timeout
                )
                logger.info(f"Received response from original file")

                # Check if response is an error (including timeout)
                if isinstance(original_response, LeanError):
                    error_msg = f"Failed to analyze original file: {original_response.message}"
                    logger.warning(error_msg)
                    return False, error_msg

                sorries_raw = (
                    original_response.sorries if original_response.sorries else []
                )
                # Convert LeanInteract Sorry objects to our format
                sorries = [
                    {
                        "location": {
                            "start_line": s.start_pos.line,
                            "start_column": s.start_pos.column,
                            "end_line": s.end_pos.line,
                            "end_column": s.end_pos.column,
                        },
                        "goal": s.goal,
                    }
                    for s in sorries_raw
                ]
            except Exception as e:
                error_msg = f"Failed to analyze original file: {e}"
                logger.warning(error_msg)
                return False, error_msg

            # Read sorries from modified file
            try:
                logger.info("Reading modified file")
                modified_response = server.run(
                    FileCommand(path=str(modified_file_path)), timeout=timeout
                )

                # Check if response is an error (including timeout)
                if isinstance(modified_response, LeanError):
                    error_msg = f"Failed to analyze modified file: {modified_response.message}"
                    logger.warning(error_msg)
                    return False, error_msg

                modified_sorries_raw = (
                    modified_response.sorries if modified_response.sorries else []
                )
                # Convert LeanInteract Sorry objects to our format
                modified_sorries = [
                    {
                        "location": {
                            "start_line": s.start_pos.line,
                            "start_column": s.start_pos.column,
                            "end_line": s.end_pos.line,
                            "end_column": s.end_pos.column,
                        },
                        "goal": s.goal,
                    }
                    for s in modified_sorries_raw
                ]
            except Exception as e:
                error_msg = f"Failed to analyze modified file: {e}"
                logger.warning(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Failed to initialize LeanInteract: {e}"
            logger.error(error_msg)
            return False, error_msg

        # Check if we have removed exactly one sorry
        if len(sorries) != len(modified_sorries) + 1:
            error_msg = "Expected one less sorry in modified file"
            logger.info(error_msg)
            return False, error_msg

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

        # Check if the sorries match up
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
                    # Check if goals match
                    if original_sorry["goal"] != modified_sorry["goal"]:
                        error_msg = "Matching sorry index, but goals do not agree"
                        logger.info(error_msg)
                        return False, error_msg
                    else:
                        match_found = True
                        break
            if not match_found:
                error_msg = "Sorries do not match up"
                logger.info(error_msg)
                return False, error_msg

        logger.info("Proof verified (using LeanInteract)")
        return True, ""


def verify_lean_interact_with_server(
    lean_server: LeanServer,
    repo_dir: Path,
    location: Location,
    proof: str,
    timeout: float = REPL_TIMEOUT,
) -> tuple[bool, str]:
    """
    Verify a proof using an existing LeanServer instance.

    This is an optimization that reuses a persistent LeanServer instead of
    creating a new one for each verification. Otherwise identical to verify_lean_interact.

    Args:
        lean_server: Existing LeanServer instance to use
        repo_dir: Path to the repository
        location: Location object containing sorry location info
        proof: The proof string to replace the sorry
        timeout: Timeout in seconds for REPL operations

    Returns:
        Tuple of (is_valid, error_message)
    """
    logger.info("Using LEAN INTERACT verify with existing server")
    # Load the original file
    file_path = location.path
    full_path = repo_dir / Path(file_path)
    original_file = full_path.read_text()

    # Obtain absolute linear character indices of sorry
    start_index = position_to_index(
        original_file, location.start_line, location.start_column
    )
    end_index = position_to_index(original_file, location.end_line, location.end_column)

    # Replace sorry with proof
    modified_file = original_file[:start_index] + proof + original_file[end_index:]
    offset = start_index - end_index + len(proof)

    # Create a temporary file in the same directory as the original file
    parent_dir = full_path.parent
    with tempfile.NamedTemporaryFile(
        suffix=".lean", dir=parent_dir, delete=True
    ) as tmp:
        logger.debug(f"Writing modified file for LeanInteract to check: {modified_file}")
        tmp.write(modified_file.encode("utf-8"))
        tmp.flush()  # Ensure all data is written to disk

        # Get the relative path from repo_dir to the temp file
        temp_path = Path(tmp.name).resolve()
        modified_file_path = temp_path.relative_to(repo_dir.resolve())

        # Quickly verify the file with lake env lean before doing full analysis
        logger.info("Checking file")
        can_build, errors = check_lean_file(
            repo_dir, modified_file_path, show_warnings=False
        )
        if not can_build:
            error_msg = f"Cannot build modified file: {errors}\n"
            logger.info(f"Cannot build modified file {errors}")
            return False, error_msg

        # Use provided LeanServer to analyze files (instead of creating new one)
        try:
            # Read sorries from original file
            try:
                logger.info(f"Reading original file with timeout {timeout}")
                original_response = lean_server.run(
                    FileCommand(path=str(file_path)), timeout=timeout
                )
                logger.info(f"Received response from original file")

                # Check if response is an error (including timeout)
                if isinstance(original_response, LeanError):
                    error_msg = f"Failed to analyze original file: {original_response.message}"
                    logger.warning(error_msg)
                    return False, error_msg

                sorries_raw = (
                    original_response.sorries if original_response.sorries else []
                )
                # Convert LeanInteract Sorry objects to our format
                sorries = [
                    {
                        "location": {
                            "start_line": s.start_pos.line,
                            "start_column": s.start_pos.column,
                            "end_line": s.end_pos.line,
                            "end_column": s.end_pos.column,
                        },
                        "goal": s.goal,
                    }
                    for s in sorries_raw
                ]
            except Exception as e:
                error_msg = f"Failed to analyze original file: {e}"
                logger.warning(error_msg)
                return False, error_msg

            # Read sorries from modified file
            try:
                logger.info("Reading modified file")
                modified_response = lean_server.run(
                    FileCommand(path=str(modified_file_path)), timeout=timeout
                )

                # Check if response is an error (including timeout)
                if isinstance(modified_response, LeanError):
                    error_msg = f"Failed to analyze modified file: {modified_response.message}"
                    logger.warning(error_msg)
                    return False, error_msg

                modified_sorries_raw = (
                    modified_response.sorries if modified_response.sorries else []
                )
                # Convert LeanInteract Sorry objects to our format
                modified_sorries = [
                    {
                        "location": {
                            "start_line": s.start_pos.line,
                            "start_column": s.start_pos.column,
                            "end_line": s.end_pos.line,
                            "end_column": s.end_pos.column,
                        },
                        "goal": s.goal,
                    }
                    for s in modified_sorries_raw
                ]
            except Exception as e:
                error_msg = f"Failed to analyze modified file: {e}"
                logger.warning(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Failed to use LeanServer: {e}"
            logger.error(error_msg)
            return False, error_msg

        # Check if we have removed exactly one sorry
        if len(sorries) != len(modified_sorries) + 1:
            error_msg = "Expected one less sorry in modified file"
            logger.info(error_msg)
            return False, error_msg

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

        # Check if the sorries match up
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
                    # Check if goals match
                    if original_sorry["goal"] != modified_sorry["goal"]:
                        error_msg = "Matching sorry index, but goals do not agree"
                        logger.info(error_msg)
                        return False, error_msg
                    else:
                        match_found = True
                        break
            if not match_found:
                error_msg = "Sorries do not match up"
                logger.info(error_msg)
                return False, error_msg

        logger.info("Proof verified (using existing LeanServer)")
        return True, ""


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
