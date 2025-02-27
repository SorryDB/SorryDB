#!/usr/bin/env python3

import os
import sys
import argparse
from sorryscraper.crawler.github_api import create_session, get_contributors

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

    try:
        session = create_session(github_token)
        contributors = get_contributors("leanprover-community/mathlib4", session)
        
        with open(args.output, "w") as f:
            for contributor in contributors:
                f.write(f"{contributor}\n")
        print(f"Complete! Contributors list saved in {args.output}")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 