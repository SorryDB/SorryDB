#!/usr/bin/env python3


import argparse
import subprocess
from pathlib import Path
import sys
import json
from git_ops import prepare_repository
from repl_api import LeanRepl, setup_repl, get_goal_parent_type

def build_lean_project(repo_path: Path):
    """Run lake commands to build the Lean project."""
    # Check if already built
    if (repo_path / "lake-manifest.json").exists() and (repo_path / ".lake" / "build").exists():
        print("Project appears to be already built, skipping build step")
        return
    
    print("Running lake exe cache get...")
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
    
    if output and "sorries" in output:
        return output["sorries"]
    return None

def should_process_file(lean_file: Path) -> bool:
    """Check if file potentially contains sorries."""
    text = lean_file.read_text()
    return any(term in text for term in ["sorry", "admit", "proof_wanted"])

def process_lean_file(relative_path: Path, repo_path: Path, repl_binary: Path) -> dict | None:
    """Process a Lean file to find sorries and their proof states.
    
    Returns:
        Dict containing:
            - file: str, relative path to the file
            - sorries: list of dicts, each containing:
                - proofState: int, identifier for the proof state
                - pos: dict with line and column of start position
                - endPos: dict with line and column of end position
                - goal: str, the goal at the sorry position
                - fullState: str, the complete proof state at this position
        Returns None if no sorries found
    """
    print(f"Processing {relative_path}...")
    
    with LeanRepl(repo_path, repl_binary) as repl:
        # First get all sorries in the file
        sorries = find_sorries_in_file(relative_path, repl)
        if not sorries:
            return None
            
        # For each sorry, get its full proof state using the same REPL instance
        for sorry in sorries:
            # Get the parent type of the goal
            parent_type = get_goal_parent_type(repl, sorry["proofState"])
            if parent_type:
                sorry["parentType"] = parent_type
            
        return {
            "file": str(relative_path),
            "sorries": sorries
        }

def process_lean_repo(repo_path: Path, lean_data: Path) -> list:
    """Process all Lean files in a repository using the REPL."""
    repl_binary = setup_repl(lean_data)
    lean_files = [(f.relative_to(repo_path), f) for f in repo_path.rglob("*.lean") 
                  if ".lake" not in f.parts and should_process_file(f)]
    
    results = []
    for rel_path, abs_path in lean_files:
        result = process_lean_file(rel_path, repo_path, repl_binary)
        if result:
            results.append(result)
    return results

def main():
    parser = argparse.ArgumentParser(description='Process Lean files in a repository using lean-repl-py.')
    parser.add_argument('--repo', type=str, required=True,
                       help='Repository to process (format: owner/repo)')
    parser.add_argument('--branch', type=str,
                       help='Branch to process (default: repository default branch)')
    parser.add_argument('--lean-data-dir', type=str, default='lean_data',
                       help='Directory for repository checkouts (default: lean_data)')
    args = parser.parse_args()
    
    lean_data = Path(args.lean_data_dir)
    lean_data.mkdir(exist_ok=True)
    
    # Clone repository
    checkout_path = prepare_repository(args.repo, args.branch, None, lean_data)
    if not checkout_path:
        print("Failed to prepare repository")
        sys.exit(1)
    
    try:
        # Build project
        build_lean_project(checkout_path)
        
        # Process Lean files
        results = process_lean_repo(checkout_path, lean_data)
        
        # Write results
        with open("output.json", "w") as f:
            json.dump(results, f, indent=2)
            
        print("Complete! Results saved in output.json")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 