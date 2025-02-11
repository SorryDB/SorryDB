#!/usr/bin/env python3

# TODO: check which sorries have type Prop, here is some wonderful tactic to do
# that:
# run_tac (do
#     let parentType ← Meta.inferType (← Tactic.getMainTarget)
#     logInfo m!"The parent type of the current goal is: {parentType}"
#   )

# oneliner:
# run_tac (do let parentType ← Meta.inferType (← Tactic.getMainTarget); logInfo m!"The parent type of the current goal is: {parentType}")

import argparse
import subprocess
from pathlib import Path
import sys
import json
from git_ops import prepare_repository
import os
from git import Repo
from repl_api import LeanRepl, setup_repl

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

def process_lean_file(relative_path: Path, repo_path: Path, repl_binary: Path) -> dict | None:
    """Process a single Lean file using the REPL. Returns None if no sorries found.
    
    Args:
        relative_path: Path to the Lean file relative to repo_path
        repo_path: Path to the repository root
        repl_binary: Path to the REPL executable
    """
    print(f"Processing {relative_path}...")
    
    with LeanRepl(repo_path, repl_binary) as repl:
        command = {"path": str(relative_path), "allTactics": True}
        output = repl.send_command(command)
        
        if output and "sorries" in output:
            return {
                "file": str(relative_path),
                "sorries": output["sorries"]
            }
        return None

def should_process_file(lean_file: Path) -> bool:
    """Check if file potentially contains sorries."""
    text = lean_file.read_text()
    return any(term in text for term in ["sorry", "admit", "proof_wanted"])

def process_lean_repo(repo_path: Path, lean_data: Path) -> list:
    """Process all Lean files in a repository using the REPL."""
    repl_binary = setup_repl(lean_data)
    lean_files = [(f.relative_to(repo_path), f) for f in repo_path.rglob("*.lean") 
                  if ".lake" not in f.parts and should_process_file(f)]
    return [process_lean_file(rel_path, repo_path, repl_binary) 
            for rel_path, abs_path in lean_files]

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