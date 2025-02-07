#!/usr/bin/env python3

import argparse
import subprocess
from pathlib import Path
import sys
import json
from git_ops import prepare_repository
from lean_repl_py import LeanREPLHandler
import os
from git import Repo

def get_default_branch(repo_path: Path) -> str:
    """Get the default branch of the repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    return result.stdout.strip()

def build_project(repo_path: Path):
    """Run lake commands to build the project."""
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

def setup_repl(lean_data: Path) -> Path:
    """Clone and build the REPL repository."""
    repl_dir = lean_data / "repl"
    if not repl_dir.exists():
        print("Cloning REPL repository...")
        repo = Repo.clone_from(
            "https://github.com/leanprover-community/repl",
            repl_dir
        )
        
        print("Building REPL...")
        result = subprocess.run(["lake", "build"], cwd=repl_dir)
        if result.returncode != 0:
            raise Exception("Failed to build REPL")
    
    repl_binary = repl_dir / ".lake" / "build" / "bin" / "repl"
    if not repl_binary.exists():
        raise Exception("REPL binary not found")
    
    # Make binary executable
    repl_binary.chmod(0o755)
    
    return repl_binary

def process_lean_files(repo_path: Path, lean_data: Path):
    """Process all .lean files using the Lean REPL directly."""
    results = []
    
    # Get REPL binary
    repl_binary = setup_repl(lean_data)
    
    print("Starting REPL process...")
    repl = subprocess.Popen(
        ["lake", "env", str(repl_binary.absolute())],
        cwd=repo_path,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    
    # Check if REPL started successfully
    if repl.poll() is not None:
        print("REPL failed to start!")
        print("stderr:", repl.stderr.read())
        raise Exception("REPL process failed to start")
    
    # Just check stderr for any warnings/errors
    stderr_line = repl.stderr.readline()
    if stderr_line:
        print(f"REPL stderr: {stderr_line}")
    
    # Skip waiting for stdout - REPL might not output anything until we send a command
    
    try:
        # Get all .lean files, excluding those in .lake directory
        lean_files = [f for f in repo_path.rglob("*.lean") 
                     if ".lake" not in f.parts]
        
        for lean_file in lean_files:
            relative_path = lean_file.relative_to(repo_path)
            print(f"Processing {relative_path}...")
            
            try:
                command = {
                    "path": str(relative_path),
                    "allTactics": True
                }
                print(f"Sending command: {json.dumps(command)}")
                repl.stdin.write(json.dumps(command) + "\n\n")  # Double newline is important
                repl.stdin.flush()
                
                # Read response
                response = ""
                while True:
                    if repl.poll() is not None:
                        print("REPL process terminated unexpectedly!")
                        print("stderr:", repl.stderr.read())
                        raise Exception("REPL process died")
                        
                    line = repl.stdout.readline()
                    if not line.strip():  # Empty line marks end of response
                        break
                    response += line
                
                output = json.loads(response) if response.strip() else None
                
            except Exception as e:
                print(f"Error processing file {relative_path}: {e}")
                output = None
            
            results.append({
                "file": str(relative_path),
                "output": output
            })
        
        return results
        
    finally:
        print("Closing REPL process...")
        repl.terminate()
        repl.wait()

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
        build_project(checkout_path)
        
        # Process Lean files
        results = process_lean_files(checkout_path, lean_data)
        
        # Write results
        with open("output.json", "w") as f:
            json.dump(results, f, indent=2)
            
        print("Complete! Results saved in output.json")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 