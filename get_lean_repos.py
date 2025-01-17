#!/usr/bin/env python3

import os
import sys
import time
import requests
from typing import List, Set
from pathlib import Path

# Configuration
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

def retry_with_backoff(func):
    """Decorator to retry functions with exponential backoff."""
    def wrapper(*args, **kwargs):
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except (requests.exceptions.RequestException, ConnectionError) as e:
                if attempt == MAX_RETRIES - 1:  # Last attempt
                    raise
                wait = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                print(f"Request failed: {e}. Retrying in {wait} seconds...")
                time.sleep(wait)
        return None
    return wrapper

@retry_with_backoff
def check_rate_limit(session: requests.Session):
    """Check and handle GitHub API rate limit."""
    response = session.get("https://api.github.com/rate_limit")
    remaining = response.json()["rate"]["remaining"]
    if remaining < 10:
        reset_time = response.json()["rate"]["reset"]
        sleep_time = reset_time - time.time() + 1
        if sleep_time > 0:
            print(f"Rate limit nearly exceeded. Waiting {sleep_time:.0f} seconds...")
            time.sleep(sleep_time)

@retry_with_backoff
def get_user_repos(user: str, session: requests.Session) -> Set[str]:
    """Get all non-fork repositories for a user."""
    repos = set()
    page = 1
    
    while True:
        response = session.get(
            f"https://api.github.com/users/{user}/repos",
            params={"page": page, "per_page": 100, "type": "owner"}
        )
        response.raise_for_status()
        
        results = response.json()
        if not results:
            break
            
        for repo in results:
            if not repo["fork"] and not repo["archived"]:
                repos.add(repo["full_name"])
        
        page += 1
    
    return repos

@retry_with_backoff
def has_lakefile(repo: str, session: requests.Session) -> bool:
    """Check if a repository has a lakefile.lean."""
    response = session.get(f"https://api.github.com/repos/{repo}/contents/lakefile.lean")
    return response.status_code == 200

def main():
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

    try:
        # Read contributors list
        if not Path("all_contributors.txt").exists():
            print("Error: all_contributors.txt not found")
            sys.exit(1)
            
        with open("all_contributors.txt") as f:
            contributors = [line.strip() for line in f if line.strip()]
        
        print(f"Processing {len(contributors)} contributors...")
        
        # Load existing repositories if any
        lean_repos = set()
        if Path("lean4_repos.txt").exists():
            with open("lean4_repos.txt") as f:
                lean_repos.update(line.strip() for line in f if line.strip())
            print(f"Loaded {len(lean_repos)} existing repositories")
        
        # Get all repositories
        for i, user in enumerate(contributors, 1):
            print(f"Processing {user} ({i}/{len(contributors)})...")
            check_rate_limit(session)
            
            try:
                repos = get_user_repos(user, session)
                for repo in repos:
                    if has_lakefile(repo, session):
                        if repo not in lean_repos:
                            lean_repos.add(repo)
                            print(f"Found new Lean repository: {repo}")
                            # Save immediately
                            with open("lean4_repos.txt", "w") as f:
                                for r in sorted(lean_repos):
                                    f.write(f"{r}\n")
            except Exception as e:
                print(f"Error processing user {user}: {e}")
                continue
        
        print(f"\nComplete! Found {len(lean_repos)} Lean repositories in total")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 