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
            if sleep_time > 0:
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
            if sleep_time > 0:
                print(f"GraphQL API rate limit nearly exceeded. Waiting {sleep_time:.0f} seconds...")
                time.sleep(sleep_time)
    except Exception as e:
        print(f"Error checking GraphQL rate limit: {e}")

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
                    if commit_cursor:  # Need to fetch more commits for this branch
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

def process_file_content(content: str) -> List[int]:
    """Process file content and return line numbers containing sorries."""
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
            sorry_lines.append(i + 1)
    
    return sorry_lines

def get_affected_files(repo: str, branch_commits: Dict[str, List[str]], session: requests.Session) -> Dict[str, List[str]]:
    """Get files affected by recent commits using REST API."""
    branch_files = {}
    
    for branch, info in branch_commits.items():
        affected_files = set()
        head_sha = info["commits"][0]  # Latest commit
        
        for commit_sha in info["commits"]:
            try:
                check_rate_limit(session)
                response = session.get(
                    f"https://api.github.com/repos/{repo}/commits/{commit_sha}"
                )
                response.raise_for_status()
                commit_data = response.json()
                
                # Add all modified .lean files that still exist
                for file_info in commit_data.get('files', []):
                    if file_info.get('filename', '').endswith('.lean'):
                        check_rate_limit(session) 
                        check_response = session.get(
                            f"https://api.github.com/repos/{repo}/contents/{file_info['filename']}",
                            params={"ref": head_sha}
                        )
                        if check_response.status_code == 200:
                            affected_files.add(file_info['filename'])
            
            except Exception as e:
                print(f"Error getting files for commit {commit_sha}: {str(e)}")
                continue
        
        if affected_files:
            branch_files[branch] = list(affected_files)
            print(f"Found {len(affected_files)} affected .lean files in branch {branch}")
    
    return branch_files

def process_repository(repo: str, session: requests.Session, cutoff_date: datetime) -> List[Dict[str, Any]]:
    """Process a repository to find sorries in recently modified files across all branches."""
    results = []
    
    try:
        # Get recent commits per branch
        branch_commits = get_recent_commits(repo, session, cutoff_date)
        
        if not branch_commits:
            print(f"Skipping {repo} - no recent commits")
            return []
            
        # Get affected files per branch
        branch_files = get_affected_files(repo, branch_commits, session)
        
        if not branch_files:
            print(f"Skipping {repo} - no affected .lean files")
            return []
            
        total_files = sum(len(files) for files in branch_files.values())
        print(f"Found {len(branch_files)} active branches with {total_files} affected .lean files")
        
        # Process each branch
        for branch, files in branch_files.items():
            print(f"Processing branch: {branch} ({len(files)} files)")
            head_sha = branch_commits[branch]["commits"][0]  # Use latest commit
            head_date = branch_commits[branch]["head_date"]
            
            # Process each file
            for file_path in files:
                try:
                    content = get_file_content_at_ref(repo, file_path, head_sha, session)
                    if not content:
                        continue
                    
                    # Find sorries
                    sorry_lines = process_file_content(content)
                    
                    for line_number in sorry_lines:
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
                            "head_sha": head_sha,
                            "head_date": head_date,
                            "file_path": file_path,
                            "github_url": f"https://github.com/{repo}/blob/{head_sha}/{file_path}#L{line_number}",
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