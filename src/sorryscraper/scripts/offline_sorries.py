#!/usr/bin/env python3


import argparse
import subprocess
from pathlib import Path
import sys
import json
import hashlib
from sorryscraper.crawler.git_ops import prepare_repository, get_git_blame_info, get_repo_metadata
from sorryscraper.repro.repl_api import LeanRepl, setup_repl, get_goal_parent_type

def hash_string(s: str) -> str:
    """Create a truncated SHA-256 hash of a string.
    Returns first 12 characters of the hex digest."""
    return hashlib.sha256(s.encode()).hexdigest()[:12]

def build_lean_project(repo_path: Path):
    """Run lake commands to build the Lean project."""
    # Check if already built
    if (repo_path / "lake-manifest.json").exists() and (repo_path / ".lake" / "build").exists():
        print("Project appears to be already built, skipping build step")
        return
    
    print("Getting build cache...")
    result = subprocess.run(["lake", "exe", "cache", "get"], cwd=repo_path)
    if result.returncode != 0:
        raise Exception("lake exe cache get failed")
    
    print("Building project...")
    result = subprocess.run(["lake", "build"], cwd=repo_path)
    if result.returncode != 0:
        raise Exception("lake build failed")

def find_sorries_in_file(relative_path: Path, repl: LeanRepl) -> list | None:
    """Find sorries in a Lean file using the REPL.
            
    Returns:
        List of sorries, where each sorry is a dict containing:
            - proofState: int, repl identifier for the proof state at the sorry
            - pos, endPos: dicts with line and column of the sorry's start and end positions
            - goal: str, the goal at the sorry position
        Returns None if no sorries found
    """
    
    command = {"path": str(relative_path), "allTactics": True}
    output = repl.send_command(command)
    
    if output is None:
        print("  REPL returned no output")
        return None
        
    if "error" in output:
        print(f"  REPL error: {output['error']}")
        return None
        
    if "sorries" not in output:
        print("  REPL output missing 'sorries' field")
        return None
        
    print(f"  REPL found {len(output['sorries'])} sorries")
    return output["sorries"]

def should_process_file(lean_file: Path) -> bool:
    """Check if file potentially contains sorries."""
    text = lean_file.read_text()
    return any(term in text for term in ["sorry", "admit", "proof_wanted"])

def process_lean_file(relative_path: Path, repo_path: Path, repl_binary: Path) -> list | None:
    """Process a Lean file to find sorries and their proof states.
    
    Returns:
        List of sorries, each containing:
            - goal: dict with goal information
                - type: str, the goal at the sorry position
                - parentType: str, the parent type of the goal (if available)
                - hash: str, hash of the goal string for duplicate detection
            - location: dict with position information
                - file: str, relative path to the file
                - startLine: int, starting line number
                - startColumn: int, starting column number
                - endLine: int, ending line number
                - endColumn: int, ending column number
            - blame: dict, git blame information for the sorry line
        Returns None if no sorries found
    """
    print(f"Processing {relative_path}...")
    
    with LeanRepl(repo_path, repl_binary) as repl:
        # First get all sorries in the file
        sorries = find_sorries_in_file(relative_path, repl)
        if not sorries:
            return None
            
        # For each sorry, get its full proof state using the same REPL instance
        results = []
        for sorry in sorries:
            # Get the parent type of the goal
            parent_type = get_goal_parent_type(repl, sorry["proofState"])
            
            # Structure the sorry information
            structured_sorry = {
                "goal": {
                    "type": sorry["goal"],
                    "hash": hash_string(sorry["goal"])
                },
                "location": {
                    "startLine": sorry["pos"]["line"],
                    "startColumn": sorry["pos"]["column"],
                    "endLine": sorry["endPos"]["line"],
                    "endColumn": sorry["endPos"]["column"]
                },
                "blame": get_git_blame_info(repo_path, relative_path, sorry["pos"]["line"])
            }
            
            # Add parent type if available
            if parent_type:
                structured_sorry["goal"]["parentType"] = parent_type
                
            results.append(structured_sorry)
            
        return results

def process_lean_repo(repo_path: Path, lean_data: Path, subdir: str | None = None, version_tag: str | None = None) -> list:
    """Process all Lean files in a repository using the REPL.
    
    Args:
        repo_path: Path to the repository root
        lean_data: Path to the lean data directory
        subdir: Optional subdirectory to restrict search to
        
    Returns:
        List of sorries, each containing:
            - goal: dict with goal information
                - type: str, the goal at the sorry position
                - parentType: str, the parent type of the goal (if available)
                - hash: str, hash of the goal string for duplicate detection
            - location: dict with position information
                - file: str, relative path to the file
                - startLine: int, starting line number
                - startColumn: int, starting column number
                - endLine: int, ending line number
                - endColumn: int, ending column number
            - blame: dict, git blame information for the sorry line
    """
    repl_binary = setup_repl(lean_data, version_tag)
    
    # Build list of files to process
    if subdir:
        search_path = repo_path / subdir
        if not search_path.exists():
            raise Exception(f"Subdirectory {subdir} does not exist")
        lean_files = [(f.relative_to(repo_path), f) for f in search_path.rglob("*.lean") 
                      if ".lake" not in f.parts and should_process_file(f)]
    else:
        lean_files = [(f.relative_to(repo_path), f) for f in repo_path.rglob("*.lean") 
                      if ".lake" not in f.parts and should_process_file(f)]
    
    print(f"Found {len(lean_files)} files containing potential sorries")
    
    results = []
    for rel_path, abs_path in lean_files:
        print(f"\nProcessing {rel_path}...")
        sorries = process_lean_file(rel_path, repo_path, repl_binary)
        if sorries:
            print(f"Found {len(sorries)} sorries")
            for sorry in sorries:
                sorry["location"]["file"] = str(rel_path)
                results.append(sorry)
        else:
            print("No sorries found (REPL processing failed or returned no results)")
    
    print(f"\nTotal sorries found: {len(results)}")
    return results

def main():
    parser = argparse.ArgumentParser(description='Process Lean files in a repository using lean-repl-py.')
    parser.add_argument('--repo-url', type=str, required=True,
                       help='Git remote URL (HTTPS or SSH) of the repository to process')
    parser.add_argument('--branch', type=str,
                       help='Branch to process (default: repository default branch)')
    parser.add_argument('--lean-data-dir', type=str, default='lean_data',
                       help='Directory for repository checkouts (default: lean_data)')
    parser.add_argument('--dir', type=str,
                       help='Subdirectory to search for Lean files (default: entire repository)')
    parser.add_argument('--lean-version-tag', type=str,
                       help='Lean version tag to used by REPL (default: most recent version of Lean available on REPL)')
    args = parser.parse_args()
    
    lean_data = Path(args.lean_data_dir)
    lean_data.mkdir(exist_ok=True)
    
    # Clone repository
    checkout_path = prepare_repository(args.repo_url, args.branch, None, lean_data)
    if not checkout_path:
        print("Failed to prepare repository")
        sys.exit(1)
    
    try:
        # Build project
        build_lean_project(checkout_path)
        
        # Process Lean files
        sorries = process_lean_repo(checkout_path, lean_data, args.dir, args.lean_version_tag)
        
        # Get repository metadata
        metadata = get_repo_metadata(checkout_path)
        
        # Combine results
        results = {
            "metadata": metadata,
            "sorries": sorries
        }
        
        # Write results
        with open("output.json", "w") as f:
            json.dump(results, f, indent=2)
            
        print("Complete! Results saved in output.json")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 
