#!/usr/bin/env python3

import json
import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sorrydb.database.process_sorries import build_lean_project
from sorrydb.utils.git_ops import prepare_repository
from sorrydb.utils.lean_repo import build_lean_project
from sorrydb.utils.repl_ops import LeanRepl, setup_repl
from sorrydb.utils.verify import verify_proof

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





def _process_sorries_with_lean_data(lean_data: Path, sorry_data: List[Dict]) -> List[Dict]:
    """Helper function that does the actual sorry processing with a given lean_data directory.

    Args:
        lean_data: path to store Lean data
        sorry_data: dict containing one sorry from the database

    Returns:
        list of proof strings or None (when no proof is found)
    """
    output = []
    for sorry in sorry_data["sorries"]:

        # Prepare the repository (clone/checkout)
        checkout_path = prepare_repository(
            sorry["repo"]["remote"],
            sorry["repo"]["branch"],
            sorry["repo"]["commit"],
            lean_data,
        )
        if not checkout_path:
            logger.error(f"Failed to prepare repository: {sorry['repo']['remote']}")
            raise Exception(f"Failed to prepare repository: {sorry['repo']['remote']}")

        # Build the Lean project
        build_lean_project(checkout_path)

        # Setup REPL
        repl_binary = setup_repl(lean_data, sorry["repo"]["lean_version"])

        # Try to apply rfl to the sorry
        proof = None
        try:
            with LeanRepl(checkout_path, repl_binary) as repl:
                proof = try_rfl(repl, sorry)
        except Exception as e:
            logger.warning(f"Error applying rfl: {e}")
 
        # If proof is not None, verify the proof
        if proof is not None:
            if not verify_proof(
                checkout_path,
                sorry["repo"]["lean_version"],
                sorry["location"],
                proof,
            ):
                proof = None
        
        # Add output dict
        output_sorry = sorry
        output_sorry["proof"] = proof
        output.append(output_sorry)

    return output

def try_rfl(repl: LeanRepl, sorry: Dict) -> str | None:
    """Try to apply rfl to a sorry.

    Args:
        repl: LeanRepl instance
        sorry: Dict containing the sorry data

    Returns:
        str if rfl was applied successfully and no goals are left, None otherwise
    """

    # Locate sorry and obtain proof_state_id
    proof_state_id, goal = repl.find_sorry_proof_state(sorry["location"])
    logger.info(f"Found sorry with goal: {goal}")

    # Apply rfl to the proof_state_id
    new_goals, new_proof_state_id = repl.apply_tactic(proof_state_id, "rfl")


    # Verify that there are no goals left
    if len(new_goals) > 0:
        logger.info(f"New goals after rfl: {new_goals}")
        return None
    else:
        logger.info("No goals left after rfl")
        return "rfl"



def process_sorries_json(
    json_path: Path, lean_data_dir: Optional[Path] = None
) -> List[Optional[str]]:
    """Process a JSON with a list of sorries.

    Args:
        json_path: Path to the sorry JSON file
        lean_data_dir: Optional path to store Lean data (default: create temporary directory)

    Returns:
        Goal state after applying `rfl`
    """
    # Load the sorry JSON
    sorry_data = load_sorry_json(json_path)

    # Use a temporary directory for lean data if not provided
    if lean_data_dir is None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lean_data = Path(temp_dir) / "lean_data"
            lean_data.mkdir(exist_ok=True)
            # Process the sorry and return the actual goal
            return _process_sorries_with_lean_data(
                lean_data,
                sorry_data,
            )
    else:
        lean_data = Path(lean_data_dir)
        lean_data.mkdir(exist_ok=True, parents=True)
        # Process the sorry and return the actual goal
        return _process_sorries_with_lean_data(
            lean_data,
            sorry_data,
        )
