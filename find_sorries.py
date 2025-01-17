#!/usr/bin/env python3

import os
import time
import requests
import sys
import argparse
from pathlib import Path
import base64
from typing import List, Dict, Any
import json
from datetime import datetime, timedelta

# Configuration
CUTOFF_DAYS = 10  # Number of days to look back for new sorries

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

def is_file_recent(repo: str, path: str, session: requests.Session, cutoff_date: datetime) -> bool:
    """Check if a file was modified after the cutoff date."""
    check_rate_limit(session)
    try:
        response = session.get(
            f"https://api.github.com/repos/{repo}/commits",
            params={
                "path": path,
                "since": cutoff_date.isoformat(),
                "per_page": 1
            }
        )
        response.raise_for_status()
        return len(response.json()) > 0
    except Exception as e:
        print(f"Error checking if file is recent: {e}")
        return False

def get_current_file_content(repo: str, path: str, session: requests.Session) -> str:
    """Get current file content."""
    check_rate_limit(session)
    try:
        response = session.get(f"https://api.github.com/repos/{repo}/contents/{path}")
        response.raise_for_status()
        return base64.b64decode(response.json()["content"]).decode("utf-8")
    except requests.RequestException as e:
        print(f"Error getting file content: {e}")
        return None

def is_lean_sorry(line: str) -> bool:
    """Check if a line contains a sorry."""
    line = line.strip()
    return line == "sorry" or line.startswith("sorry ")

def extract_imports(content: str) -> List[str]:
    """Extract all import statements from a Lean file."""
    imports = []
    for line in content.splitlines():
        if line.strip().startswith('--'):
            continue
        if line.strip().startswith('import '):
            import_path = line.strip()[7:].split('--')[0].strip()
            imports.append(import_path)
    return sorted(imports)

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

def get_latest_commit_date(repo: str, session: requests.Session) -> datetime:
    """Get the date of the latest commit in the repository."""
    check_rate_limit(session)
    try:
        response = session.get(
            f"https://api.github.com/repos/{repo}/commits",
            params={"per_page": 1}
        )
        response.raise_for_status()
        commits = response.json()
        if commits:
            return datetime.fromisoformat(commits[0]["commit"]["committer"]["date"].replace("Z", "+00:00"))
        return None
    except Exception as e:
        print(f"Error getting latest commit date: {e}")
        return None

def process_repository(repo: str, session: requests.Session, cutoff_date: datetime) -> List[Dict[str, Any]]:
    """Process a repository to find sorries in recently modified files."""
    print(f"Processing {repo}...")
    
    try:
        # Check if repository has any recent commits
        latest_commit_date = get_latest_commit_date(repo, session)
        if not latest_commit_date or latest_commit_date < cutoff_date:
            print(f"Skipping {repo} - no recent commits")
            return []

        # Get all current .lean files
        response = session.get(
            f"https://api.github.com/repos/{repo}/git/trees/HEAD",
            params={"recursive": "1"}
        )
        response.raise_for_status()
        
        files = [item for item in response.json()["tree"] 
                if item["type"] == "blob" and item["path"].endswith(".lean")]
        
        # Skip if repo contains mathlib
        if any("/mathlib4/" in f["path"] or "/Mathlib/" in f["path"] for f in files):
            print(f"Skipping {repo} - contains mathlib files")
            return []
        
        results = []
        for file in files:
            try:
                # Check if file was modified recently
                if not is_file_recent(repo, file["path"], session, cutoff_date):
                    continue
                
                # Get current version
                content = get_current_file_content(repo, file["path"], session)
                if not content:
                    continue
                                
                # Find all sorries in this file
                lines = content.splitlines()
                
                for i, line in enumerate(lines):
                    if is_lean_sorry(line):
                        line_number = i + 1
                        
                        # Get blame info for this sorry
                        blame_info = get_line_blame_info(repo, file["path"], line_number, session)
                        if not blame_info:
                            continue
                            
                        # Skip if the sorry is older than cutoff date
                        blame_date = datetime.fromisoformat(blame_info["date"].replace("Z", "+00:00"))
                        if blame_date < cutoff_date:
                            continue
                        
                        results.append({
                            "repository": repo,
                            "file_path": file["path"],
                            "github_url": f"https://github.com/{repo}/blob/HEAD/{file['path']}#L{line_number}",
                            "line_number": line_number,
                            "blame_date": blame_info["date"]
                        })
            
            except Exception as e:
                print(f"Error processing file {file['path']}: {e}")
                continue
        
        return results
    
    except Exception as e:
        print(f"Error processing repository {repo}: {e}")
        return []

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