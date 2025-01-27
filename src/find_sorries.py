#!/usr/bin/env python3

import os
import sys
import argparse
from typing import List, Dict, Any
import json
from datetime import datetime, timedelta
import requests
from github_api import (
    create_session,
    get_file_content,
    get_blame_info,
    get_recent_branch_data,
    get_affected_files_for_branch
)
from sorry_finder import find_recent_sorries_in_branch



def find_sorry_lines(content: str) -> List[Dict[str, Any]]:
    """Find line numbers and content of lines containing 'sorry' tokens."""
    lines = content.splitlines()
    sorry_lines = []
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Skip line comments
        if line.startswith("--") or line.startswith("/--"):
            continue
            
        # Look for 'sorry' as a token
        parts = line.split()
        if 'sorry' in parts:
            sorry_lines.append({
                "line_number": i + 1,
                "content": line
            })
    
    return sorry_lines

def get_active_branches(branch_data: List[Dict]) -> Dict[str, Dict[str, str]]:
    """Extract active branch info from branch data."""
    branches = {}
    for branch in branch_data:
        if branch['target']['history']['nodes']:  # Has commits since cutoff
            branches[branch['name']] = {
                "head_sha": branch['target']['oid'],
                "head_date": branch['target']['committedDate']
            }
    return branches

def process_branch(repo: str, branch_name: str, head_info: Dict[str, str], cutoff_date: datetime, session: requests.Session) -> List[Dict[str, Any]]:
    """Process a single branch to find sorries in recently modified files."""
    results = []
    
    # Get affected files for this branch
    affected_files = get_affected_files_for_branch(repo, head_info["head_sha"], cutoff_date, session)
    if not affected_files:
        return []
        
    print(f"Processing branch: {branch_name} ({len(affected_files)} files)")
    
    # Process each file
    for file_path in affected_files:
        try:
            content = get_file_content(repo, file_path, head_info["head_sha"], session)
            if not content:
                continue
            
            # Find sorries
            sorry_lines = find_sorry_lines(content)
            
            for sorry in sorry_lines:
                # Get blame info using the branch's head SHA
                blame_info = get_blame_info(repo, file_path, sorry["line_number"], head_info["head_sha"], session)
                if not blame_info:
                    continue
                    
                # Skip if sorry is older than cutoff
                blame_date = datetime.fromisoformat(blame_info["date"].replace("Z", "+00:00"))
                if blame_date < cutoff_date:
                    continue
                
                results.append({
                    "repository": repo,
                    "branch": branch_name,
                    "head_sha": head_info["head_sha"],
                    "head_date": head_info["head_date"],
                    "file_path": file_path,
                    "github_url": f"https://github.com/{repo}/blob/{head_info['head_sha']}/{file_path}#L{sorry['line_number']}",
                    "line_number": sorry["line_number"],
                    "line_content": sorry["content"],
                    "blame": blame_info
                })
        
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")
            continue
    
    return results

def process_repository(repo: str, session: requests.Session, cutoff_date: datetime) -> List[Dict[str, Any]]:
    """Process a repository to find sorries in recently modified files across all branches."""
    try:
        # Get active branches
        branch_data = get_recent_branch_data(repo, cutoff_date, session)
        branches = get_active_branches(branch_data)
        if not branches:
            return []
        
        # Process each branch and combine results
        results = []
        for branch_name, head_info in branches.items():
            results.extend(process_branch(repo, branch_name, head_info, cutoff_date, session))
        
        return results
    
    except Exception as e:
        print(f"Error processing repository {repo}: {e}")
        return []

def main():
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description='Find recent sorries in a Lean repository.')
    parser.add_argument('--repository', type=str, required=True,
                       help='Repository to check (format: owner/name)')
    parser.add_argument('--cutoff', type=int, default=10,
                       help='Number of days to look back for new sorries (default: 10)')
    parser.add_argument('--output', type=str, default='new_sorries.json',
                       help='Output file path (default: new_sorries.json)')
    args = parser.parse_args()

    # Check for GitHub token
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        print("Error: GITHUB_TOKEN environment variable is not set")
        sys.exit(1)

    # Setup session with retry logic
    session = create_session(github_token)

    # Set cutoff date using the command line argument
    cutoff_date = datetime.now(datetime.now().astimezone().tzinfo) - timedelta(days=args.cutoff)
    print(f"Checking for sorries in files modified since: {cutoff_date.strftime('%Y-%m-%d')}")

    # Process repository
    print(f"\nProcessing {args.repository}...")
    branch_data = get_recent_branch_data(args.repository, cutoff_date, session)
    branches = get_active_branches(branch_data)
    print(f"Found {len(branches)} active branches")
    
    results = []
    for branch_name, head_info in branches.items():
        branch_results = find_recent_sorries_in_branch(args.repository, branch_name, head_info, cutoff_date, session)
        if branch_results:
            print(f"Found {len(branch_results)} sorries in {args.repository}@{branch_name}")
            results.extend(branch_results)
            with open(args.output, "w") as f:
                json.dump(results, f, indent=2)

    print(f"\nComplete! Results saved in {args.output}")

if __name__ == "__main__":
    main() 