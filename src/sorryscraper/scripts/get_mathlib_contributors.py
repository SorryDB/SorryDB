#!/usr/bin/env python3

import os
import sys
import requests
from typing import List
import argparse

def get_contributors(session: requests.Session) -> List[str]:
    """Get all contributors to mathlib4."""
    contributors = set()
    page = 1
    
    while True:
        response = session.get(
            "https://api.github.com/repos/leanprover-community/mathlib4/contributors",
            params={"page": page, "per_page": 100}
        )
        response.raise_for_status()
        
        results = response.json()
        if not results:
            break
            
        for contributor in results:
            contributors.add(contributor["login"])
        
        page += 1
    # leanprover-community itself not returned as a contributor
    contributors.add("leanprover-community")
    return sorted(contributors)

def main():
    parser = argparse.ArgumentParser(description='Get Mathlib contributors from GitHub.')
    parser.add_argument('--output', type=str, required=True,
                       help='Output file path for contributors list')
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

    try:
        contributors = get_contributors(session)
        with open(args.output, "w") as f:
            for contributor in contributors:
                f.write(f"{contributor}\n")
        print(f"Complete! Contributors list saved in {args.output}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 