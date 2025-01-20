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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def create_session(token):
    """Create a session with retry logic and authentication."""
    session = requests.Session()
    
    # Configure retry strategy
    retry_strategy = Retry(
        total=8,  # number of retries
        backoff_factor=1,  # wait 1, 2, ..., 128 seconds between retries
        status_forcelist=[429, 500, 502, 503, 504],  # HTTP status codes to retry on
        allowed_methods=["GET", "POST"],  # Allow retries on both GET and POST
        # Also retry on connection errors and timeouts
        raise_on_status=False,
        raise_on_redirect=False,
        connect=5,  # retries on connection errors
        read=5     # retries on read errors/timeouts
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    # Add authentication
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    })
    
    return session

def check_rate_limit(session):
    """Check both GraphQL and REST API rate limits."""
    # Check REST API rate limit
    try:
        response = session.get('https://api.github.com/rate_limit')
        response.raise_for_status()
        data = response.json()
        rest_remaining = data['resources']['core']['remaining']
        rest_reset = datetime.fromtimestamp(data['resources']['core']['reset'])
        
        if rest_remaining < 10:
            sleep_time = (rest_reset - datetime.now()).total_seconds() + 1
            print(f"REST API rate limit nearly exceeded. Waiting {sleep_time:.0f} seconds...")
            time.sleep(sleep_time)
    except Exception as e:
        print(f"Error checking REST rate limit: {e}")

    # Check GraphQL API rate limit
    query = """
    query {
      rateLimit {
        remaining
        resetAt
      }
    }
    """
    
    try:
        response = session.post(
            'https://api.github.com/graphql',
            json={'query': query}
        )
        data = response.json()
        graphql_remaining = data['data']['rateLimit']['remaining']
        reset_at = datetime.fromisoformat(data['data']['rateLimit']['resetAt'].replace('Z', '+00:00'))
        
        if graphql_remaining < 10:
            sleep_time = (reset_at - datetime.now(datetime.now().astimezone().tzinfo)).total_seconds() + 1
            print(f"GraphQL API rate limit nearly exceeded. Waiting {sleep_time:.0f} seconds...")
            time.sleep(sleep_time)
    except Exception as e:
        print(f"Error checking GraphQL rate limit: {e}")

def get_line_blame_info(repo: str, path: str, line_number: int, ref: str, session: requests.Session) -> Dict[str, Any]:
    """Get blame information for a specific line using GraphQL."""
    check_rate_limit(session)
    owner, name = repo.split('/')
    query = """
    query ($owner: String!, $name: String!, $path: String!, $ref: String!) {
      repository(owner: $owner, name: $name) {
        object(expression: $ref) {
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
    """
    
    variables = {
        "owner": owner,
        "name": name,
        "path": path,
        "ref": ref  # Now using the passed ref instead of hardcoded "HEAD"
    }
    
    try:
        response = session.post(
            'https://api.github.com/graphql',
            json={'query': query, 'variables': variables}
        )
        response.raise_for_status()
        data = response.json()
        
        # Navigate through the response to find the blame range for our line
        ranges = data['data']['repository']['object']['blame']['ranges']
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

def get_recent_commits(repo: str, session: requests.Session, cutoff_date: datetime) -> Dict[str, List[str]]:
    """Get recent commits for each active branch.
    Returns a dict mapping branch_name -> list of commit SHAs, ordered from newest to oldest.
    Only includes branches that have had commits since cutoff_date."""
    owner, repo_name = repo.split('/')
    query = """
    query ($owner: String!, $name: String!, $since: GitTimestamp!, $branchCursor: String, $commitCursor: String) {
      repository(owner: $owner, name: $name) {
        refs(refPrefix: "refs/heads/", first: 100, after: $branchCursor) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            name
            target {
              ... on Commit {
                history(first: 100, after: $commitCursor, since: $since) {
                  pageInfo {
                    hasNextPage
                    endCursor
                  }
                  nodes {
                    oid
                  }
                }
                committedDate
              }
            }
          }
        }
      }
    }
    """
    
    branch_commits = {}
    branch_cursor = None
    
    try:
        # Keep fetching branches until we've got them all
        while True:
            check_rate_limit(session)  # Add check before GraphQL call
            variables = {
                "owner": owner,
                "name": repo_name,
                "since": cutoff_date.isoformat(),
                "branchCursor": branch_cursor,
                "commitCursor": None
            }
            
            response = session.post(
                'https://api.github.com/graphql',
                json={'query': query, 'variables': variables}
            )
            response.raise_for_status()
            data = response.json()
            
            if 'errors' in data:
                print(f"GraphQL errors: {json.dumps(data['errors'], indent=2)}")
                return {}
                
            if 'data' not in data or data['data'] is None:
                print(f"Unexpected GraphQL response")
                return {}
                
            if 'repository' not in data['data'] or data['data']['repository'] is None:
                print(f"Repository not found or no access")
                return {}
            
            refs_data = data['data']['repository']['refs']
            if refs_data is None:
                print(f"No refs data")
                return {}
            
            # Process each branch
            for branch in refs_data['nodes']:
                branch_name = branch['name']
                target = branch['target']
                if target is None:
                    continue
                    
                commits = []
                commit_cursor = None
                
                # Keep fetching commits for this branch until we've got them all
                while True:
                    if commit_cursor:
                        check_rate_limit(session)  # Add check before commit query
                        variables["commitCursor"] = commit_cursor
                        commit_response = session.post(
                            'https://api.github.com/graphql',
                            json={'query': query, 'variables': variables}
                        )
                        commit_response.raise_for_status()
                        commit_data = commit_response.json()
                        
                        if 'errors' in commit_data:
                            break
                            
                        history = commit_data['data']['repository']['refs']['nodes'][0]['target']['history']
                    else:  # First page of commits is in our initial response
                        history = target['history']
                    
                    if history is None:
                        break
                    
                    # Add commits from this page
                    commits.extend(commit['oid'] for commit in history['nodes'])
                    
                    # Check if we need to get more commits
                    if not history['pageInfo']['hasNextPage']:
                        break
                    commit_cursor = history['pageInfo']['endCursor']
                
                # Only include branches that have commits
                if commits:
                    branch_commits[branch_name] = {
                        "commits": commits,
                        "head_date": target['committedDate']
                    }
            
            # Check if we need to get more branches
            if not refs_data['pageInfo']['hasNextPage']:
                break
            branch_cursor = refs_data['pageInfo']['endCursor']
        
        return branch_commits
        
    except Exception as e:
        print(f"Error getting recent commits for {repo}: {e}")
        return {}

def get_file_content_at_ref(repo: str, path: str, ref: str, session: requests.Session) -> str:
    """Get file content at a specific ref using GraphQL."""
    check_rate_limit(session)
    owner, name = repo.split('/')
    query = """
    query ($owner: String!, $name: String!, $path: String!, $ref: String!) {
      repository(owner: $owner, name: $name) {
        object(expression: $ref) {
          ... on Commit {
            file(path: $path) {
              object {
                ... on Blob {
                  text
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
        "path": path,
        "ref": ref
    }
    
    try:
        response = session.post(
            'https://api.github.com/graphql',
            json={'query': query, 'variables': variables}
        )
        response.raise_for_status()
        data = response.json()
        
        # Check for GraphQL errors
        if 'errors' in data:
            print(f"GraphQL errors getting content for {path}@{ref}: {data['errors']}")
            return None
            
        # Safely navigate the response structure
        repository = data.get('data', {}).get('repository')
        if not repository:
            print(f"No repository data for {path}@{ref}")
            return None
            
        obj = repository.get('object')
        if not obj:
            print(f"No object data for {path}@{ref}")
            return None
            
        file_data = obj.get('file')
        if not file_data:
            print(f"No file data for {path}@{ref}")
            return None
            
        file_obj = file_data.get('object')
        if not file_obj:
            print(f"No file object for {path}@{ref}")
            return None
            
        text = file_obj.get('text')
        if text is None:
            print(f"No text content for {path}@{ref}")
            return None
            
        return text
        
    except Exception as e:
        print(f"Error getting file content for {path}@{ref}: {e}")
        return None

def process_file_content(content: str) -> List[Dict[str, Any]]:
    """Process file content and return line numbers and content containing sorries."""
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

def get_active_branches(repo: str, session: requests.Session, cutoff_date: datetime) -> Dict[str, Dict[str, str]]:
    """Get active branches that have commits since cutoff_date.
    Returns dict mapping branch_name -> {"head_sha": sha, "head_date": date}"""
    owner, repo_name = repo.split('/')
    query = """
    query ($owner: String!, $name: String!, $since: GitTimestamp!, $cursor: String) {
      repository(owner: $owner, name: $name) {
        refs(refPrefix: "refs/heads/", first: 100, after: $cursor) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            name
            target {
              ... on Commit {
                history(first: 1, since: $since) {
                  nodes {
                    oid
                  }
                }
                oid
                committedDate
              }
            }
          }
        }
      }
    }
    """
    
    branches = {}
    cursor = None
    
    try:
        while True:
            check_rate_limit(session)  # Add check before GraphQL call
            variables = {
                "owner": owner,
                "name": repo_name,
                "since": cutoff_date.isoformat(),
                "cursor": cursor
            }
            
            response = session.post(
                'https://api.github.com/graphql',
                json={'query': query, 'variables': variables}
            )
            response.raise_for_status()
            data = response.json()
            
            if 'errors' in data:
                print(f"GraphQL errors: {json.dumps(data['errors'], indent=2)}")
                return {}
            
            refs_data = data['data']['repository']['refs']
            
            # Process branches from this page
            for branch in refs_data['nodes']:
                # Only include branches with commits since cutoff
                if branch['target']['history']['nodes']:
                    branches[branch['name']] = {
                        "head_sha": branch['target']['oid'],
                        "head_date": branch['target']['committedDate']
                    }
            
            # Check if we need to get more branches
            if not refs_data['pageInfo']['hasNextPage']:
                break
            cursor = refs_data['pageInfo']['endCursor']
        
        return branches
        
    except Exception as e:
        print(f"Error getting active branches for {repo}: {e}")
        return {}

def get_affected_files_for_branch(repo: str, branch_name: str, head_info: Dict[str, str], cutoff_date: datetime, session: requests.Session) -> List[str]:
    """Get files affected since cutoff_date for a single branch using GitHub's compare API."""
    try:
        # Get the commit SHA from cutoff_date for this branch
        check_rate_limit(session)
        response = session.get(
            f"https://api.github.com/repos/{repo}/commits",
            params={
                "sha": head_info["head_sha"],
                "until": cutoff_date.isoformat(),
                "per_page": 1
            }
        )
        response.raise_for_status()
        commits = response.json()
        if not commits:
            return []
        
        base_sha = commits[0]["sha"]
        
        # Compare base to head to get all file changes
        check_rate_limit(session)
        response = session.get(
            f"https://api.github.com/repos/{repo}/compare/{base_sha}...{head_info['head_sha']}"
        )
        response.raise_for_status()
        compare_data = response.json()
        
        # Return all modified .lean files that still exist
        affected_files = [
            file['filename'] 
            for file in compare_data['files'] 
            if file['filename'].endswith('.lean') and file['status'] != 'removed'
        ]
                
        return affected_files
    
    except Exception as e:
        print(f"Error getting files for branch {branch_name}: {str(e)}")
        return []

def process_branch(repo: str, branch_name: str, head_info: Dict[str, str], cutoff_date: datetime, session: requests.Session) -> List[Dict[str, Any]]:
    """Process a single branch to find sorries in recently modified files."""
    results = []
    
    # Get affected files for this branch
    affected_files = get_affected_files_for_branch(repo, branch_name, head_info, cutoff_date, session)
    if not affected_files:
        return []
        
    print(f"Processing branch: {branch_name} ({len(affected_files)} files)")
    
    # Process each file
    for file_path in affected_files:
        try:
            content = get_file_content_at_ref(repo, file_path, head_info["head_sha"], session)
            if not content:
                continue
            
            # Find sorries
            sorry_lines = process_file_content(content)
            
            for sorry in sorry_lines:
                # Get blame info using the branch's head SHA
                blame_info = get_line_blame_info(repo, file_path, sorry["line_number"], head_info["head_sha"], session)
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
        branches = get_active_branches(repo, session, cutoff_date)
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
    parser = argparse.ArgumentParser(description='Find recent sorries in Lean repositories.')
    parser.add_argument('--cutoff', type=int, default=10,
                       help='Number of days to look back for new sorries (default: 10)')

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