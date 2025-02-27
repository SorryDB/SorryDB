#!/usr/bin/env python3

import argparse
from pathlib import Path
import json

from sorrydb.database.build_database import build_database

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
    

    results = build_database(
        repo_url=args.repo_url,
        branch=args.branch,
        lean_data=lean_data,
        subdir=args.dir,
        lean_version_tag=args.lean_version_tag
    )
    
    # Write results
    with open("output.json", "w") as f:
        json.dump(results, f, indent=2)
        
    print("Complete! Results saved in output.json") 
        

if __name__ == "__main__":
    main() 
