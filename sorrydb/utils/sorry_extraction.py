#!/usr/bin/env python3

import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
from sorrydb.utils.repl_ops import setup_repl, LeanRepl
from abc import abstractmethod

logger = logging.getLogger(__name__)

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
        # For now, the flag should always be false
        self.repl_binary = setup_repl(lean_data, version_string)

    """ A wrapper function for REPL functionalities. This processes a Lean file to extract all sorries
        using the REPL, and the removes all sorries that aren't of type Prop. """
    def extract_sorries(self, repo_path:Path, relative_file_path:Path) -> list[dict] : 
        # repl = setup_repl(lean_data, version_string)
        repl = LeanRepl(repo_path, self.repl_binary)
        sorries = repl.read_file(relative_file_path)
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

""" Initalise a sorry extractor using the REPL or another method. For now only
the REPL version has been implemented. """
def initialise_sorry_extractor(lean_data:Path, version_string:str, is_repl = True) :
    if not is_repl : 
        raise RuntimeError("Only the REPL sorry extractor has been implemented for now.")
    return ReplSorryExtractor(lean_data, version_string)