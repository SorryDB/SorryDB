#!/usr/bin/env python3

import json
import logging
import subprocess
import os
from pathlib import Path
from typing import List, Optional, Tuple
from sorrydb.utils.repl_ops import setup_repl, LeanRepl
from sorrydb.utils.leanutils_ops import setup_leanutils
from abc import abstractmethod

logger = logging.getLogger(__name__)


class SorryExtractor:
    """ Class for abstracting away sorry extraction methods. """

    """ Extract all sorries in a lean file using the extraction method and return them as a dictionary. """
    @abstractmethod
    def extract_sorries(self, repo_path: Path, relative_path_to_file: Path) -> list[dict]:
        pass


class LeanSorryExtractor(SorryExtractor):

    """Stores a path to a Lean binary that can be used to
    perform sorry extraction. 
    """

    def __init__(self, lean_data: Path, version_string: str):
        self.lean_extractor_binary = setup_leanutils(lean_data, version_string)

    """ A wrapper function for the SorryDB/LeanUtils LeanExtractor. This processes a Lean file to extract all
    Prop-valued sorries """

    def extract_sorries(self, repo_path: Path, relative_file_path: Path) -> list[dict]:
        cmd = [
            "lake",
            "env",
            "lean",
            "--run",
            str(self.lean_extractor_binary.absolute()),
            os.path.join(repo_path, relative_file_path)
        ]
        logger.debug("Running command: %s", " ".join(cmd))

        process = subprocess.Popen(
            cmd,
            cwd=repo_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        # self.process.stdin.write(json.dumps(command) + "\n\n")
        # self.process.stdin.flush()

        response = ""
        while True:
            if process.poll() is not None:
                error = process.stderr.read()
                logger.error("LeanExtractor died: %s", error)
                raise RuntimeError(f"LeanExtractor died: {error}")

            line = process.stdout.readline()
            if not line.strip():
                break
            response += line

        logger.debug("Raw LeanExtractor response: %s", response.strip())
        result = json.loads(response)

        # # Check for error messages (old REPL code, LeanUtils does not output error messages to stdout)
        # messages = result.get("messages", [])
        # error_messages = [m["data"]
        #                   for m in messages if m.get("severity") == "error"]
        # if error_messages:
        #     raise ReplError(
        #         f"LeanExtractor returned errors: {'; '.join(error_messages)}")

        return result  # lake env lean --run bins/ExtractSorry.lean LeanUtilsTest/LeanFileWithSorries.lean


class ReplSorryExtractor(SorryExtractor):

    """Stores a path to a Lean binary that can be used to
    perform sorry extraction. 
    """

    def __init__(self, lean_data: Path, version_string: str):
        self.repl_binary = setup_repl(lean_data, version_string)

    """ A wrapper function for REPL functionalities. This processes a Lean file to extract all sorries
        using the REPL, and the removes all sorries that aren't of type Prop. """

    def extract_sorries(self, repo_path: Path, relative_file_path: Path) -> list[dict]:
        with LeanRepl(repo_path, self.repl_binary) as repl:
            sorries = repl.read_file(relative_file_path)
            prop_sorries = []
            for sorry in sorries:
                # Don't include sorries that aren't of type "Prop"
                try:
                    parent_type = repl.get_goal_parent_type(
                        sorry["proof_state_id"])
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


def initialise_sorry_extractor(lean_data: Path, version_string: str, use_repl):
    if not use_repl:
        return LeanSorryExtractor(lean_data, version_string)
    else:
        return ReplSorryExtractor(lean_data, version_string)
