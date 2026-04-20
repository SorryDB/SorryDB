#!/usr/bin/env python3

import difflib
import logging
from pathlib import Path
from sorrydb.utils.repl_ops import setup_repl, LeanRepl
from sorrydb.utils.verify_lean_interact import position_to_index
from sorrydb.database.sorry import Location
from abc import abstractmethod

logger = logging.getLogger(__name__)


def extract_proof_from_diff(
    original: str, llm_output: str, location: Location
) -> str | None:
    """Extract the proof that replaced 'sorry' by diffing original vs LLM output."""
    # Strip markdown code blocks - use last COMPLETE block only
    if "```lean" in llm_output:
        # Find all complete ```lean ... ``` blocks
        parts = llm_output.split("```lean")
        complete_blocks = []
        for part in parts[1:]:  # Skip text before first ```lean
            if "```" in part:
                # This block has a closing ``` - it's complete
                block_content = part.split("```")[0]
                complete_blocks.append(block_content)

        # Use last complete block, or skip stripping if none found
        if complete_blocks:
            llm_output = complete_blocks[-1]
        # else: no complete blocks, use llm_output as-is (skip stripping)

    original = original.replace("sorry", "獏獏獏獏獏").rstrip()
    llm_output = llm_output.replace("sorry", "獏獏獏獏獏").rstrip()
    
    llm_output = llm_output.strip("`").strip()

    sorry_start = position_to_index(
        original, location.start_line, location.start_column
    )
    sorry_end = position_to_index(original, location.end_line, location.end_column)

    matcher = difflib.SequenceMatcher(None, original, llm_output, autojunk=False)
    blocks = matcher.get_matching_blocks()

    # Find blocks before and after the sorry position
    block_before = None
    block_after = None

    for i, j, n in blocks:
        block_end_orig = i + n

        # Check if block starts before sorry
        if i < sorry_start:
            if block_end_orig <= sorry_start:
                # Block ends before sorry - use as-is
                block_before = (i, j, n)

        # Check if block starts at or after sorry ends
        if i >= sorry_end and block_after is None:
            block_after = (i, j, n)
            break

    if block_before is None or block_after is None:
        return None

    # Extract proof: from end of block_before to start of block_after in llm_output
    proof_start = block_before[1] + block_before[2]
    proof_end = block_after[1]

    # Look back past spaces/tabs for a newline and include it
    i = proof_start - 1
    while i >= 0 and llm_output[i] in " \t":
        i -= 1
    if i >= 0 and llm_output[i] == "\n":
        proof_start = i

    return llm_output[proof_start:proof_end].replace("獏獏獏獏獏", "sorry")

class SorryExtractor : 
    """ Class for abstracting away sorry extraction methods. """

    
    """ Extract all sorries in a lean file using the extraction method and return them as a dictionary. """
    @abstractmethod 
    def extract_sorries(self, repo_path: Path, relative_path_to_file:Path) -> list[dict] :
        pass

class ReplSorryExtractor(SorryExtractor) :
    
    """Stores a path to a Lean binary that can be used to
    perform sorry extraction. 
    
    Note: For now the flag use_repl should not be used and will throw an
    error if it is used...
    """
    def __init__(self, lean_data:Path, version_string:str) :
        self.repl_binary = setup_repl(lean_data, version_string)

    """ A wrapper function for REPL functionalities. This processes a Lean file to extract all sorries
        using the REPL, and the removes all sorries that aren't of type Prop. """
    def extract_sorries(self, repo_path:Path, relative_file_path:Path) -> list[dict] : 
        with LeanRepl(repo_path, self.repl_binary) as repl:
            # Get all sorries in the file using repl.read_file with a 15-minute timeout
            sorries = repl.read_file(relative_file_path, timeout=900)
            prop_sorries = []
            for sorry in sorries:
            # Don't include sorries that aren't of type "Prop"
                try:
                    parent_type = repl.get_goal_parent_type(sorry["proof_state_id"])
                except RuntimeError as e:
                    logger.warning(f"Runtime error getting parent type: {e}")
                    parent_type = None
                if parent_type != "Prop":
                    logger.debug(
                        f"Skipping sorry {sorry['goal']} in {relative_file_path} not of type `Prop`"
                    )
                    continue
                prop_sorries.append(sorry)
            return prop_sorries
            

""" Initalise a sorry extractor using the REPL or another method. For now only
the REPL version has been implemented. """
def initialise_sorry_extractor(lean_data:Path, version_string:str, is_repl = True) :
    if not is_repl : 
        raise RuntimeError("Only the REPL sorry extractor has been implemented for now.")
    return ReplSorryExtractor(lean_data, version_string)
