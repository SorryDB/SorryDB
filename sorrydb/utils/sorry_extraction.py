#!/usr/bin/env python3

import difflib
import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
from sorrydb.utils.repl_ops import setup_repl, LeanRepl
from sorrydb.utils.verify_lean_interact import position_to_index
from sorrydb.database.sorry import Location
from abc import abstractmethod

logger = logging.getLogger(__name__)


def extract_proof_from_diff(
    original: str, llm_output: str, location: Location
) -> str | None:
    """Extract the proof that replaced 'sorry' by diffing original vs LLM output."""
    # Strip markdown code blocks
    if "```lean" in llm_output:
        llm_output = llm_output.split("```lean")[-1].split("```")[0]
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
            else:
                # Block overlaps sorry - truncate at sorry_start
                truncated_n = sorry_start - i
                block_before = (i, j, truncated_n)

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

    return llm_output[proof_start:proof_end]

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
            sorries = repl.read_file(relative_file_path)
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
