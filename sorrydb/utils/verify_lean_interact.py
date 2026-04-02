#!/usr/bin/env python3

import logging
import tempfile
from pathlib import Path

from lean_interact import FileCommand, LeanREPLConfig, LeanServer, LocalProject
from lean_interact.interface import LeanError
from sorrydb.database.sorry import Location

from .repl_ops import check_lean_file

logger = logging.getLogger(__name__)

REPL_TIMEOUT = 500


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
                logger.info("Received response from original file")

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


class VerificationContext:
    """
    Maintains a LeanServer and cached original file data for efficient
    repeated proof verification against the same sorry location.

    This class is optimized for pass@k scenarios where multiple proofs need
    to be verified against the same sorry. It initializes the LeanServer and
    analyzes the original file once, then reuses them for each verification.

    Usage:
        ctx = VerificationContext(repo_dir, location)
        for proof in proofs:
            success, error = ctx.verify_proof(proof)
    """

    def __init__(
        self, repo_dir: Path, location: Location, timeout: float = REPL_TIMEOUT
    ):
        """
        Initialize the verification context.

        Args:
            repo_dir: Path to the repository
            location: Location object containing sorry location info
            timeout: Timeout in seconds for REPL operations
        """
        self.repo_dir = repo_dir
        self.location = location
        self.timeout = timeout

        # Cached data (populated in _initialize)
        self._original_file: str
        self._original_sorries: list[dict]
        self._start_index: int
        self._end_index: int
        self._server: LeanServer

        self._initialize()

    def _initialize(self) -> None:
        """Initialize server and cache original file data."""
        logger.info("Initializing VerificationContext")

        file_path = self.location.path
        full_path = self.repo_dir / Path(file_path)
        self._original_file = full_path.read_text()

        # Compute position indices ONCE
        self._start_index = position_to_index(
            self._original_file, self.location.start_line, self.location.start_column
        )
        self._end_index = position_to_index(
            self._original_file, self.location.end_line, self.location.end_column
        )

        # Create LeanServer ONCE
        logger.info("Creating LeanServer for VerificationContext")
        project = LocalProject(directory=str(self.repo_dir.resolve()))
        config = LeanREPLConfig(project=project, verbose=False)
        self._server = LeanServer(config)

        # Analyze original file ONCE
        logger.info(f"Analyzing original file {file_path} with timeout {self.timeout}")
        original_response = self._server.run(
            FileCommand(path=str(file_path)), timeout=self.timeout
        )
        if isinstance(original_response, LeanError):
            raise RuntimeError(
                f"Failed to analyze original file: {original_response.message}"
            )

        sorries_raw = original_response.sorries or []
        self._original_sorries = [
            {
                "location": {
                    "start_line": s.start_pos.line,
                    "start_column": s.start_pos.column,
                    "end_line": s.end_pos.line,
                    "end_column": s.end_pos.column,
                },
                "goal": s.goal,
                "index": position_to_index(
                    self._original_file, s.start_pos.line, s.start_pos.column
                ),
            }
            for s in sorries_raw
        ]
        logger.info(
            f"VerificationContext initialized with {len(self._original_sorries)} sorries"
        )

    def verify_proof(self, proof: str) -> tuple[bool, str]:
        """
        Verify a proof against the cached sorry location.

        Args:
            proof: The proof string to replace the sorry

        Returns:
            Tuple of (is_valid, error_message) where:
            - is_valid: Boolean indicating whether the proof is valid
            - error_message: Empty string if valid, otherwise error description
        """
        logger.info("VerificationContext.verify_proof called")

        # 1. Create modified file content
        modified_file = (
            self._original_file[: self._start_index]
            + proof
            + self._original_file[self._end_index :]
        )
        offset = self._start_index - self._end_index + len(proof)

        # 2. Write temp file and quick build check
        full_path = self.repo_dir / Path(self.location.path)
        parent_dir = full_path.parent

        with tempfile.NamedTemporaryFile(
            suffix=".lean", dir=parent_dir, delete=True
        ) as tmp:
            tmp.write(modified_file.encode("utf-8"))
            tmp.flush()

            temp_path = Path(tmp.name).resolve()
            modified_file_path = temp_path.relative_to(self.repo_dir.resolve())

            # Quick build check
            logger.info("Running quick build check")
            can_build, errors = check_lean_file(
                self.repo_dir, modified_file_path, show_warnings=False
            )
            if not can_build:
                error_msg = f"Cannot build modified file: {errors}"
                logger.info(error_msg)
                return False, error_msg

            # 3. Analyze modified file with EXISTING server
            logger.info("Analyzing modified file with existing server")
            try:
                modified_response = self._server.run(
                    FileCommand(path=str(modified_file_path)), timeout=self.timeout
                )
            except Exception as e:
                error_msg = f"Failed to analyze modified file: {e}"
                logger.warning(error_msg)
                return False, error_msg

            if isinstance(modified_response, LeanError):
                error_msg = (
                    f"Failed to analyze modified file: {modified_response.message}"
                )
                logger.warning(error_msg)
                return False, error_msg

            modified_sorries_raw = modified_response.sorries or []
            modified_sorries = [
                {
                    "location": {
                        "start_line": s.start_pos.line,
                        "start_column": s.start_pos.column,
                        "end_line": s.end_pos.line,
                        "end_column": s.end_pos.column,
                    },
                    "goal": s.goal,
                    "index": position_to_index(
                        modified_file, s.start_pos.line, s.start_pos.column
                    ),
                }
                for s in modified_sorries_raw
            ]

        # 4. Compare against CACHED original sorries
        return self._compare_sorries(modified_sorries, offset)

    def _compare_sorries(
        self, modified_sorries: list[dict], offset: int
    ) -> tuple[bool, str]:
        """
        Compare modified sorries against cached original sorries.

        Args:
            modified_sorries: List of sorry dicts from the modified file
            offset: Character offset due to proof replacement

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check count - should have exactly one less sorry
        if len(self._original_sorries) != len(modified_sorries) + 1:
            error_msg = "Expected one less sorry in modified file"
            logger.info(error_msg)
            return False, error_msg

        # Check each original sorry has a match (except the one we replaced)
        for original_sorry in self._original_sorries:
            if original_sorry["index"] == self._start_index:
                continue  # Skip the replaced sorry

            expected_index = original_sorry["index"]
            if original_sorry["index"] > self._start_index:
                expected_index += offset

            match_found = False
            for modified_sorry in modified_sorries:
                if modified_sorry["index"] == expected_index:
                    if original_sorry["goal"] != modified_sorry["goal"]:
                        error_msg = "Matching sorry index, but goals do not agree"
                        logger.info(error_msg)
                        return False, error_msg
                    match_found = True
                    break

            if not match_found:
                error_msg = "Sorries do not match up"
                logger.info(error_msg)
                return False, error_msg

        logger.info("Proof verified (using VerificationContext)")
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
