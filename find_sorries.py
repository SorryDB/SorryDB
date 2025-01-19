#!/usr/bin/env python3

import os
import time
import requests
import sys
import argparse
from pathlib import Path
import base64
from typing import List, Dict, Any, Set
import json
from datetime import datetime, timedelta

def check_rate_limit(session):
    """Check GitHub API rate limit status."""
    response = session.get("https://api.github.com/rate_limit")
    remaining = response.json()["rate"]["remaining"]
    if remaining < 10:
        reset_time = response.json()["rate"]["reset"]
        sleep_time = reset_time - time.time() + 1
        if sleep_time > 0:
            print(f"Rate limit nearly exceeded. Waiting {sleep_time:.0f} seconds...")
            time.sleep(sleep_time)

def is_lean_sorry(line: str) -> bool:
    """Check if a line contains a sorry."""
    line = line.strip()
    return line == "sorry" or line.startswith("sorry ")

def get_line_blame_info(repo: str, path: str, line_number: int, session: requests.Session) -> Dict[str, Any]:
    """Get blame information for a specific line using GraphQL."""
    owner, name = repo.split('/')
    query = """
    query ($owner: String!, $name: String!, $path: String!) {
      repository(owner: $owner, name: $name) {
        defaultBranchRef {
          target {
            ... on Commit {
              blame(path: $path) {
                ranges {
                  startingLine
                  endingLine
                  commit {
                    authoredDate
                    author {
                      name
                      email
                    }
                    message
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    
    variables = {
        "owner": owner,
        "name": name,
        "path": path
    }
    
    try:
        response = session.post(
            'https://api.github.com/graphql',
            json={'query': query, 'variables': variables}
        )
        response.raise_for_status()
        data = response.json()
        
        # Navigate through the response to find the blame range for our line
        ranges = data['data']['repository']['defaultBranchRef']['target']['blame']['ranges']
        for range_info in ranges:
            if range_info['startingLine'] <= line_number <= range_info['endingLine']:
                commit = range_info['commit']
                return {
                    "author": commit['author']['name'],
                    "email": commit['author']['email'],
                    "date": commit['authoredDate'],
                    "message": commit['message'].split('\n')[0]  # First line only
                }
        return None
    except Exception as e:
        print(f"Error getting blame for {path}:{line_number}: {e}")
        return None

def get_recent_branches(repo: str, session: requests.Session, cutoff_date: datetime) -> List[str]:
    """Get all branches that have had commits after the cutoff date."""
    check_rate_limit(session)
    active_branches = set()
    page = 1
    
    while True:
        try:
            # Get all commits after cutoff date
            response = session.get(
                f"https://api.github.com/repos/{repo}/commits",
                params={
                    "since": cutoff_date.isoformat(),
                    "page": page,
                    "per_page": 100
                }
            )
            response.raise_for_status()
            results = response.json()
            if not results:
                break
            
            # For each commit, get its branches
            for commit in results:
                branch_response = session.get(
                    f"https://api.github.com/repos/{repo}/commits/{commit['sha']}/branches-where-head"
                )
                if branch_response.status_code == 200:
                    branches = branch_response.json()
                    active_branches.update(branch["name"] for branch in branches)
            
            page += 1
        except Exception as e:
            print(f"Error getting commits for {repo}: {e}")
            break
    
    return sorted(active_branches)

def get_modified_files(repo: str, commit_sha: str, session: requests.Session) -> Set[str]:
    """Get all files modified in a specific commit."""
    check_rate_limit(session)
    try:
        response = session.get(f"https://api.github.com/repos/{repo}/commits/{commit_sha}")
        response.raise_for_status()
        return {file["filename"] for file in response.json()["files"] 
                if file["filename"].endswith(".lean")}
    except Exception as e:
        print(f"Error getting modified files for commit {commit_sha}: {e}")
        return set()

def get_file_content_at_ref(repo: str, path: str, ref: str, session: requests.Session) -> str:
    """Get file content at a specific ref (branch or commit)."""
    check_rate_limit(session)
    try:
        response = session.get(
            f"https://api.github.com/repos/{repo}/contents/{path}",
            params={"ref": ref}
        )
        response.raise_for_status()
        return base64.b64decode(response.json()["content"]).decode("utf-8")
    except requests.RequestException as e:
        print(f"Error getting file content: {e}")
        return None

def process_repository(repo: str, session: requests.Session, cutoff_date: datetime) -> List[Dict[str, Any]]:
    """Process a repository to find sorries in recently modified files across all branches."""
    print(f"Processing {repo}...")
    results = []
    
    try:
        # Get branches with recent commits
        active_branches = get_recent_branches(repo, session, cutoff_date)
        if not active_branches:
            print(f"Skipping {repo} - no recent commits")
            return []
            
        print(f"Found {len(active_branches)} active branches")
        
        # Process each branch
        for branch in active_branches:
            print(f"Processing branch: {branch}")
            
            # Get all modified files from recent commits
            modified_files = set()
            response = session.get(
                f"https://api.github.com/repos/{repo}/commits",
                params={
                    "sha": branch,
                    "since": cutoff_date.isoformat(),
                    "per_page": 100
                }
            )
            response.raise_for_status()
            
            for commit in response.json():
                modified_files.update(get_modified_files(repo, commit["sha"], session))
            
            # Get the latest commit SHA for this branch
            latest_commit = response.json()[0]["sha"]
            
            # Process each modified file
            for file_path in modified_files:
                try:
                    # Get current content
                    content = get_file_content_at_ref(repo, file_path, latest_commit, session)
                    if not content:
                        continue
                    
                    # Find sorries
                    lines = content.splitlines()
                    for i, line in enumerate(lines):
                        if is_lean_sorry(line):
                            line_number = i + 1
                            
                            # Get blame info
                            blame_info = get_line_blame_info(repo, file_path, line_number, session)
                            if not blame_info:
                                continue
                                
                            # Skip if sorry is older than cutoff
                            blame_date = datetime.fromisoformat(blame_info["date"].replace("Z", "+00:00"))
                            if blame_date < cutoff_date:
                                continue
                            
                            results.append({
                                "repository": repo,
                                "branch": branch,
                                "commit_sha": latest_commit,
                                "file_path": file_path,
                                "github_url": f"https://github.com/{repo}/blob/{latest_commit}/{file_path}#L{line_number}",
                                "line_number": line_number,
                                "blame": blame_info
                            })
                
                except Exception as e:
                    print(f"Error processing file {file_path}: {e}")
                    continue
    
    except Exception as e:
        print(f"Error processing repository {repo}: {e}")
    
    return results

def main():
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description='Find recent sorries in Lean repositories.')
    parser.add_argument('--cutoff', type=int, default=10,
                       help='Number of days to look back for new sorries (default: 10)')

    args = parser.parse_args()

    # Check for GitHub token
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        print("Error: GITHUB_TOKEN environment variable is not set")
        sys.exit(1)

    # Setup session with authentication
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json"
    })

    # Set cutoff date using the command line argument
    cutoff_date = datetime.now(datetime.now().astimezone().tzinfo) - timedelta(days=args.cutoff)
    print(f"Checking for sorries in files modified since: {cutoff_date.strftime('%Y-%m-%d')}")

    # Read repository list
    try:
        with open("lean4_repos.txt") as f:
            repos = [line.strip() for line in f if line.strip()]
        print(f"Found {len(repos)} repositories in lean4_repos.txt")
    except FileNotFoundError:
        print("Error: lean4_repos.txt not found")
        sys.exit(1)

    # Process repositories
    results = []
    for i, repo in enumerate(repos, 1):
        print(f"\nProcessing {repo} ({i}/{len(repos)})...")
        repo_results = process_repository(repo, session, cutoff_date)
        if repo_results:
            results.extend(repo_results)
            # Save after each successful repository
            with open("new_sorries.json", "w") as f:
                json.dump(results, f, indent=2)

    print(f"\nComplete! Results saved in new_sorries.json")

    # Print summary
    repos_with_sorries = len({r["repository"] for r in results})
    files_with_sorries = len({(r["repository"], r["file_path"]) for r in results})
    total_sorries = len(results)
    
    print(f"\nSummary:")
    print(f"Repositories with sorries: {repos_with_sorries}")
    print(f"Files with sorries: {files_with_sorries}")
    print(f"Total sorry occurrences: {total_sorries}")

if __name__ == "__main__":
    main() 