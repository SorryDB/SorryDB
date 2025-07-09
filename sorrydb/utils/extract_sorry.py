#!/usr/bin/env python3

import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class LeanExtractorError(RuntimeError):
    """Class for error messages from the Lean extractor."""
    pass


# Version mapping for ExtractSorry.lean scripts
# This will map Lean versions to the appropriate ExtractSorry.lean script paths
LEAN_VERSION_TO_EXTRACTOR = {
    "v4.17.0": "/home/paul/Documents/Dev/SorryDB/LeanUtils/LeanUtils/ExtractSorry.lean",
    "v4.17.0-rc1": "/home/paul/Documents/Dev/SorryDB/LeanUtils/LeanUtils/ExtractSorry.lean",
    # Add more versions as needed
    "default": "/home/paul/Documents/Dev/SorryDB/LeanUtils/LeanUtils/ExtractSorry.lean"
}


def get_extractor_script_path(lean_version: str) -> Path:
    """Get the appropriate ExtractSorry.lean script for a given Lean version.
    
    Args:
        lean_version: The Lean version string (e.g., "v4.17.0")
        
    Returns:
        Path to the ExtractSorry.lean script
        
    Raises:
        FileNotFoundError: If no script exists for the given version
    """
    script_path = LEAN_VERSION_TO_EXTRACTOR.get(lean_version) or LEAN_VERSION_TO_EXTRACTOR["default"]
    path = Path(script_path)
    
    if not path.exists():
        raise FileNotFoundError(f"ExtractSorry script not found at {path}")
    
    return path


class LeanExtractor:
    """Interface to extract sorries from Lean files using ExtractSorry.lean scripts."""
    
    def __init__(self, repo_path: Path, lean_version: str):
        """Initialize the Lean extractor.
        
        Args:
            repo_path: Path to the repository root (used as working directory)
            lean_version: Lean version to determine which extractor script to use
        """
        self.repo_path = repo_path
        self.lean_version = lean_version
        self.extractor_script = get_extractor_script_path(lean_version)
        
        logger.info(f"Using ExtractSorry script: {self.extractor_script}")
        logger.info(f"Working directory: {repo_path}")

    def extract_sorries_from_file(self, relative_path: Path) -> List[dict]:
        """Extract sorries from a single Lean file.
        
        Args:
            relative_path: Path to the file relative to repo root
            
        Returns:
            List of dictionaries containing sorry information:
            - statement: The sorry goal/statement
            - pos: Position information with line/column
            - parentDecl: Parent declaration name
            
        Raises:
            LeanExtractorError: If extraction fails
        """
        full_path = self.repo_path / relative_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")
        
        logger.debug(f"Extracting sorries from {relative_path}")
        
        # Run the ExtractSorry.lean script
        cmd = ["lake", "env", "lean", "--run", str(self.extractor_script), str(full_path)]
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"ExtractSorry failed for {relative_path}: {result.stderr}")
                raise LeanExtractorError(f"ExtractSorry failed: {result.stderr}")
            
            # Parse the JSON output from stderr (that's where the script outputs)
            lines = result.stderr.strip().split('\n')
            if len(lines) < 2:
                logger.warning(f"Unexpected output format from ExtractSorry: {result.stderr}")
                return []
                
            # Skip the "File extraction yielded" line and parse the JSON
            json_text = '\n'.join(lines[1:])  # Join all lines after the first
            logger.debug(f"Raw JSON text: {json_text}")
            sorries = json.loads(json_text)
            
            logger.debug(f"Found {len(sorries)} sorries in {relative_path}")
            return sorries
            
        except subprocess.TimeoutExpired:
            raise LeanExtractorError(f"ExtractSorry timed out for {relative_path}")
        except json.JSONDecodeError as e:
            raise LeanExtractorError(f"Failed to parse JSON output: {e}")
        except Exception as e:
            raise LeanExtractorError(f"Unexpected error: {e}")

    def read_file(self, relative_path: Path) -> List[dict]:
        """Extract sorries from a file and convert to repl_ops.py compatible format.
        
        This method provides compatibility with the existing repl_ops.py interface.
        
        Args:
            relative_path: Path to the file relative to repo root
            
        Returns:
            List of dictionaries containing:
            - proof_state_id: Not applicable for ExtractSorry, set to None
            - location: Position information with start/end line/column
            - goal: The sorry statement/goal
        """
        raw_sorries = self.extract_sorries_from_file(relative_path)
        
        converted_sorries = []
        for sorry in raw_sorries:
            # Convert ExtractSorry format to repl_ops format
            converted_sorry = {
                "proof_state_id": None,  # Not applicable for ExtractSorry
                "location": {
                    "start_line": sorry["pos"]["line"],
                    "start_column": sorry["pos"]["column"],
                    "end_line": sorry["pos"]["line"],  # ExtractSorry only provides start position
                    "end_column": sorry["pos"]["column"] + 5,  # Assume "sorry" is 5 chars
                },
                "goal": sorry["statement"],
                "parent_decl": sorry["parentDecl"]
            }
            converted_sorries.append(converted_sorry)
        
        return converted_sorries


def setup_lean_extractor(repo_path: Path, lean_version: str) -> LeanExtractor:
    """Set up and return a LeanExtractor instance.
    
    Args:
        repo_path: Path to the repository root
        lean_version: Lean version string
        
    Returns:
        Configured LeanExtractor instance
    """
    return LeanExtractor(repo_path, lean_version)


def extract_sorries_from_repo(
    repo_path: Path, 
    lean_version: str,
    file_filter: Optional[callable] = None
) -> List[dict]:
    """Extract sorries from all Lean files in a repository.
    
    Args:
        repo_path: Path to the repository root
        lean_version: Lean version string
        file_filter: Optional function to filter which files to process
        
    Returns:
        List of sorry dictionaries with file path information added
    """
    extractor = setup_lean_extractor(repo_path, lean_version)
    
    # Find all .lean files
    lean_files = list(repo_path.rglob("*.lean"))
    
    # Filter out .lake directory files
    lean_files = [f for f in lean_files if ".lake" not in f.parts]
    
    # Apply custom filter if provided
    if file_filter:
        lean_files = [f for f in lean_files if file_filter(f)]
    
    results = []
    for lean_file in lean_files:
        try:
            relative_path = lean_file.relative_to(repo_path)
            sorries = extractor.read_file(relative_path)
            
            # Add file path to each sorry
            for sorry in sorries:
                sorry["file_path"] = str(relative_path)
                results.append(sorry)
                
        except Exception as e:
            logger.warning(f"Error processing {lean_file}: {e}")
    
    logger.info(f"Found {len(results)} total sorries in repository")
    return results


def should_process_file(lean_file: Path) -> bool:
    """Check if file potentially contains sorries.
    
    This is a simple heuristic that checks if 'sorry' appears in the file.
    This can speed up processing by filtering out files that don't need processing.
    """
    try:
        text = lean_file.read_text()
        return "sorry" in text
    except Exception:
        return True  # If we can't read the file, assume it should be processed


def process_lean_file_extract_sorry(relative_path: Path, repo_path: Path, lean_version: str) -> List[dict]:
    """Process a Lean file to find sorries using ExtractSorry.lean.
    
    This function mimics the interface of process_sorries.py:process_lean_file()
    but uses ExtractSorry.lean instead of REPL.
    
    Args:
        relative_path: Path to the file relative to repo root
        repo_path: Path to the repository root
        lean_version: Lean version string
        
    Returns:
        List of sorries, each containing:
            - goal: The sorry statement/goal
            - location: Position information with start/end line/column
            - parent_decl: Parent declaration name
    """
    extractor = setup_lean_extractor(repo_path, lean_version)
    
    try:
        sorries = extractor.read_file(relative_path)
        
        # Convert to format expected by process_sorries.py
        results = []
        for sorry in sorries:
            structured_sorry = {
                "goal": sorry["goal"],
                "location": {
                    "start_line": sorry["location"]["start_line"],
                    "start_column": sorry["location"]["start_column"],
                    "end_line": sorry["location"]["end_line"],
                    "end_column": sorry["location"]["end_column"],
                },
                "parent_decl": sorry["parent_decl"]
            }
            results.append(structured_sorry)
            
        return results
        
    except Exception as e:
        logger.warning(f"Error processing {relative_path}: {e}")
        return []