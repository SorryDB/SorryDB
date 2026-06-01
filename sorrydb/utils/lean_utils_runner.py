"""Utilities for running LeanUtils binaries (ExtractSorry and ExtractGoal)."""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import TypedDict

from sorrydb.database.sorry import Sorry

logger = logging.getLogger(__name__)


class Location(TypedDict):
    start_line: int
    start_column: int
    end_line: int
    end_column: int


class ParsedSorry(TypedDict):
    goal: str
    location: Location
    parentDecl: str
    hash: int


def run_extract_sorry(
    lean_utils_path: Path, repo_path: Path, file_path: Path
) -> list[ParsedSorry]:
    """Run ExtractSorry via `lake env lean --run` to get all sorries in a file.

    Runs from within the target repository context so that lake uses the target
    repo's Lean environment and file imports resolve correctly.

    Args:
        lean_utils_path: Path to the LeanUtils repository
        repo_path: Path to the target repository (used as cwd)
        file_path: Path to the Lean file to extract sorries from

    Returns:
        List of ParsedSorry dictionaries

    Raises:
        RuntimeError: If the command fails or returns an error
    """
    script_path = (lean_utils_path / "bins" / "ExtractSorry.lean").absolute()
    # cwd is set to repo_path below, so file_path must be absolute or it won't resolve.
    repo_path = repo_path.absolute()
    file_path = file_path.absolute()

    # Debug logging for paths
    logger.info(f"ExtractSorry paths:")
    logger.info(f"  lean_utils_path: {lean_utils_path}")
    logger.info(f"  repo_path (cwd): {repo_path}")
    logger.info(f"  file_path: {file_path}")
    logger.info(f"  script_path: {script_path}")
    logger.info(f"  script_path exists: {script_path.exists()}")
    logger.info(f"  repo_path exists: {repo_path.exists()}")
    logger.info(f"  file_path exists: {file_path.exists()}")

    # Check for lakefile in various locations
    lakefile_toml = repo_path / "lakefile.toml"
    lakefile_lean = repo_path / "lakefile.lean"
    logger.info(f"  lakefile.toml at repo_path: {lakefile_toml.exists()} ({lakefile_toml})")
    logger.info(f"  lakefile.lean at repo_path: {lakefile_lean.exists()} ({lakefile_lean})")

    # Check if lakefile is in parent of file_path
    file_parent = file_path.parent
    while file_parent != repo_path and file_parent != file_parent.parent:
        parent_lakefile_toml = file_parent / "lakefile.toml"
        parent_lakefile_lean = file_parent / "lakefile.lean"
        if parent_lakefile_toml.exists() or parent_lakefile_lean.exists():
            logger.warning(f"  Found lakefile in file's parent directory: {file_parent}")
            logger.warning(f"    lakefile.toml: {parent_lakefile_toml.exists()}")
            logger.warning(f"    lakefile.lean: {parent_lakefile_lean.exists()}")
        file_parent = file_parent.parent

    cmd = [
        "lake",
        "env",
        "lean",
        "--run",
        str(script_path),
        str(file_path),
    ]

    logger.info(f"Running ExtractSorry: {' '.join(cmd)}")

    env = {**os.environ, "LEAN_PATH": str(lean_utils_path / ".lake/build/lib/lean")}

    result = subprocess.run(
        cmd,
        cwd=repo_path,
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode != 0:
        logger.error(f"ExtractSorry failed with return code {result.returncode}")
        logger.error(f"stdout: {result.stdout}")
        logger.error(f"stderr: {result.stderr}")
        raise RuntimeError(f"ExtractSorry failed: {result.stderr}")

    # Parse the JSON output
    try:
        output = json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse ExtractSorry output: {result.stdout}")
        raise RuntimeError(f"Failed to parse ExtractSorry output: {e}") from e

    # ExtractSorry outputs a bare JSON list of ParsedSorry, or {"error": "..."} on failure
    if isinstance(output, dict) and "error" in output:
        raise RuntimeError(f"ExtractSorry returned error: {output['error']}")

    parsed_sorries: list[ParsedSorry] = output if isinstance(output, list) else output.get("ok", [])
    logger.info(f"ExtractSorry found {len(parsed_sorries)} sorries")

    return parsed_sorries


def match_sorry_to_parsed_sorry(
    sorry: Sorry, parsed_sorries: list[ParsedSorry]
) -> ParsedSorry | None:
    """Match a SorryDB Sorry to a LeanUtils ParsedSorry by position.

    The matching is done by comparing the start position (line and column).
    LeanUtils uses 1-indexed positions, matching SorryDB's Location.

    Args:
        sorry: The SorryDB Sorry object
        parsed_sorries: List of ParsedSorry dictionaries from ExtractSorry

    Returns:
        The matching ParsedSorry or None if no match is found
    """
    loc = sorry.location

    for parsed in parsed_sorries:
        # Both use 1-indexed line and column numbers
        ploc = parsed["location"]
        if (
            ploc["start_line"] == loc.start_line
            and ploc["start_column"] == loc.start_column
        ):
            logger.info(
                f"Matched sorry at {loc.start_line}:{loc.start_column} "
                f"to ParsedSorry with goal: {parsed['goal'][:50]}..."
            )
            return parsed

    logger.warning(
        f"No ParsedSorry match found for sorry at {loc.start_line}:{loc.start_column}"
    )
    return None


def run_extract_goal(
    lean_utils_path: Path, repo_path: Path, file_path: Path, parsed_sorry_json: str
) -> str:
    """Run ExtractGoal via `lake env lean --run` to generate a synthetic theorem.

    Runs from within the target repository context so that lake uses the target
    repo's Lean environment and file imports resolve correctly.

    Args:
        lean_utils_path: Path to the LeanUtils repository
        repo_path: Path to the target repository (used as cwd)
        file_path: Path to the Lean file containing the sorry
        parsed_sorry_json: JSON string of the ParsedSorry object

    Returns:
        The synthetic theorem file content

    Raises:
        RuntimeError: If the command fails or returns an error
    """
    script_path = (lean_utils_path / "bins" / "ExtractGoal.lean").absolute()
    repo_path = repo_path.absolute()
    file_path = file_path.absolute()

    # Debug logging for paths
    logger.info(f"ExtractGoal paths:")
    logger.info(f"  lean_utils_path: {lean_utils_path}")
    logger.info(f"  repo_path (cwd): {repo_path}")
    logger.info(f"  file_path: {file_path}")
    logger.info(f"  script_path: {script_path}")

    cmd = [
        "lake",
        "env",
        "lean",
        "--run",
        str(script_path),
        str(file_path),
        parsed_sorry_json,
    ]

    logger.info(f"Running ExtractGoal: {' '.join(cmd[:5])}...")
    logger.debug(f"Full ExtractGoal command: {' '.join(cmd)}")

    env = {**os.environ, "LEAN_PATH": str(lean_utils_path / ".lake/build/lib/lean")}

    result = subprocess.run(
        cmd,
        cwd=repo_path,
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode != 0:
        logger.error(f"ExtractGoal failed with return code {result.returncode}")
        logger.error(f"stdout: {result.stdout}")
        logger.error(f"stderr: {result.stderr}")
        raise RuntimeError(f"ExtractGoal failed: {result.stderr}")

    # Parse the JSON output
    try:
        output = json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse ExtractGoal output: {result.stdout}")
        raise RuntimeError(f"Failed to parse ExtractGoal output: {e}") from e

    # ExtractGoal outputs {"ok": "..."} or {"error": "..."}
    if "error" in output:
        raise RuntimeError(f"ExtractGoal returned error: {output['error']}")

    synthetic_content = output.get("ok", "")
    logger.info(f"ExtractGoal generated synthetic theorem ({len(synthetic_content)} chars)")

    return synthetic_content
