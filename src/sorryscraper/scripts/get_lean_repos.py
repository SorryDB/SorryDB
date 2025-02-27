#!/usr/bin/env python3

import os
import sys
from pathlib import Path
from sorryscraper.crawler.github_api import create_session, get_user_repos, has_lakefile

def main():
    # Check for GitHub token
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        print("Error: GITHUB_TOKEN environment variable is not set")
        sys.exit(1)

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
        
        # Setup session
        session = create_session(github_token)
        
        # Get all repositories
        for i, user in enumerate(contributors, 1):
            print(f"Processing {user} ({i}/{len(contributors)})...")
            
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