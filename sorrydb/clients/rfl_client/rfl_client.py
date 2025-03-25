#!/usr/bin/env python3

import json
import logging
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple

from database.process_sorries import build_lean_project
from utils.git_ops import prepare_repository
from utils.lean_repo import build_lean_project
from utils.repl_ops import LeanRepl, setup_repl

# Create a module-level logger
logger = logging.getLogger(__name__)


def load_sorry_json(json_path: Path) -> Dict:
    """Load a sorry JSON file.

    Args:
        json_path: Path to the sorry JSON file

    Returns:
        Dict containing the sorry data

    Raises:
        FileNotFoundError: If the JSON file doesn't exist
        json.JSONDecodeError: If the JSON file is invalid
    """
    logger.info(f"Loading sorry JSON from {json_path}")
    try:
        with open(json_path, "r") as f:
            sorry_data = json.load(f)
        return sorry_data
    except FileNotFoundError:
        logger.error(f"Sorry JSON file not found: {json_path}")
        raise
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in sorry file: {json_path}")
        raise


def find_sorry_proof_state(repl: LeanRepl, location: Dict) -> Tuple[int, str]:
    """Find the proof state ID for a sorry in a Lean file.

    Args:
        repl: An active REPL instance
        location: Dict containing the sorry location information

    Returns:
        Tuple of (proof_state_id, goal_type)

    Raises:
        Exception: If the sorry cannot be found or verified
    """
    file = location["file"]
    logger.info(f"Finding sorry proof state in {file}...")

    command = {"path": str(file), "allTactics": True}
    output = repl.send_command(command)

    if output is None:
        logger.error("REPL returned no output")
        raise Exception("REPL returned no output")

    if "error" in output:
        logger.error(f"REPL error: {output['error']}")
        raise Exception(f"REPL error: {output['error']}")

    if "sorries" not in output:
        logger.error("REPL output missing 'sorries' field")
        raise Exception("REPL output missing 'sorries' field")

    sorries = output["sorries"]
    logger.info(f"REPL found {len(sorries)} sorries in {file}")

    # Find the sorry that matches the location
    for sorry in sorries:
        if (
            sorry["pos"]["line"] == location["start_line"]
            and sorry["pos"]["column"] == location["start_column"]
            and sorry["endPos"]["line"] == location["end_line"]
            and sorry["endPos"]["column"] == location["end_column"]
        ):
            logger.info(f"Found matching sorry at line {location['start_line']}")
            return sorry["proofState"], sorry["goal"]
    logger.error("Could not find matching sorry")
    raise Exception(f"Could not find sorry at specified location: {location}")


def _process_sorry_with_lean_data(
    lean_data: Path,
    sorry_data: Dict,
) -> str | None:
    """Helper function that does the actual sorry processing with a given lean_data directory.

    Args:
        lean_data: path to store Lean data
        sorry_data: dict containing one sorry from the database

    Returns:
        proof string or None
    """
    # Prepare the repository (clone/checkout)
    checkout_path = prepare_repository(
        sorry_data["repo"]["remote"],
        sorry_data["repo"]["branch"],
        sorry_data["repo"]["commit"],
        lean_data,
    )
    if not checkout_path:
        logger.error(f"Failed to prepare repository: {sorry_data['repo']['remote']}")
        raise Exception(f"Failed to prepare repository: {sorry_data['repo']['remote']}")

    # Build the Lean project
    build_lean_project(checkout_path)

    # Setup REPL
    repl_binary = setup_repl(lean_data, sorry_data["repo"]["lean_version"])
    repl = LeanRepl(checkout_path, repl_binary)

    # Locate sorry and obtain proof_state_id
    try:
        proof_state_id, goal = find_sorry_proof_state(
            repl,
            sorry_data["location"],
        )
        logger.info(f"Found sorry with goal: {goal}")
    except Exception as e:
        logger.error(f"Error finding sorry proof state: {e}")
        raise Exception(f"Error finding sorry proof state: {e}")

    # Apply rfl to the proof_state_id
    result = repl.apply_tactic(proof_state_id, "rfl")
    if result is None:
        logger.warning("rfl tactic failed")
        return None
    new_proof_state_id, new_goals = result
    if len(new_goals) == 0:
        logger.info("No goals left after rfl")
        return "rfl"
    else:
        logger.info(f"New goals after rfl: {new_goals}")
        return None


def process_sorry_json(json_path: Path, lean_data_dir: Optional[Path] = None) -> str:
    """Process a sorry JSON file and attempt to close the goal using rfl.

    Args:
        json_path: Path to the sorry JSON file
        lean_data_dir: Optional path to store Lean data (default: create temporary directory)

    Returns:
        Goal state after applying `rfl`
    """
    # Load the sorry JSON
    sorry_data = load_sorry_json(json_path)

    # TODO: validate sorry_data

    # Use a temporary directory for lean data if not provided
    if lean_data_dir is None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lean_data = Path(temp_dir) / "lean_data"
            lean_data.mkdir(exist_ok=True)
            # Process the sorry and return the actual goal
            return _process_sorry_with_lean_data(
                lean_data,
                sorry_data,
            )
    else:
        lean_data = Path(lean_data_dir)
        lean_data.mkdir(exist_ok=True, parents=True)
        # Process the sorry and return the actual goal
        return _process_sorry_with_lean_data(
            lean_data,
            sorry_data,
        )
