from datetime import datetime
from typing import Dict, List, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json

# Core session and rate limit handling
def create_session(token: str) -> requests.Session:
    """Create authenticated session with retry logic"""
    session = requests.Session()
    
    retry_strategy = Retry(
        total=8,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
        raise_on_redirect=False,
        connect=5,
        read=5
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    })
    
    return session

def check_rate_limit(session: requests.Session) -> None:
    """Check both GraphQL and REST API rate limits"""
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

# Basic GraphQL queries
def graphql_query(session: requests.Session, query: str, variables: Dict) -> Optional[Dict]:
    """Execute a GraphQL query and return the result"""
    check_rate_limit(session)
    try:
        response = session.post(
            'https://api.github.com/graphql',
            json={'query': query, 'variables': variables}
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"GraphQL query error: {e}")
        return None

# REST API operations
def get_commit_at_date(repo: str, ref: str, date: datetime, session: requests.Session) -> Optional[str]:
    """Get the last commit SHA before given date on a ref"""
    check_rate_limit(session)
    try:
        response = session.get(
            f"https://api.github.com/repos/{repo}/commits",
            params={
                "sha": ref,
                "until": date.isoformat(),
                "per_page": 1
            }
        )
        response.raise_for_status()
        commits = response.json()
        return commits[0]["sha"] if commits else None
    except Exception as e:
        print(f"Error getting commit at date: {e}")
        return None

def get_modified_files(repo: str, base_sha: str, head_sha: str, session: requests.Session) -> List[str]:
    """Get list of modified files between two commits"""
    check_rate_limit(session)
    try:
        response = session.get(
            f"https://api.github.com/repos/{repo}/compare/{base_sha}...{head_sha}"
        )
        response.raise_for_status()
        compare_data = response.json()
        
        return [
            file['filename'] 
            for file in compare_data['files'] 
            if file['filename'].endswith('.lean') and file['status'] != 'removed'
        ]
    except Exception as e:
        print(f"Error getting modified files: {e}")
        return []

def get_file_content(repo: str, path: str, ref: str, session: requests.Session) -> Optional[str]:
    """Get content of a file at specific ref using GraphQL."""
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
    
    data = graphql_query(session, query, variables)
    if not data:
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

def get_blame_info(repo: str, path: str, line: int, ref: str, session: requests.Session) -> Optional[Dict]:
    """Get blame information for a specific line using GraphQL."""
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
        "ref": ref
    }
    
    data = graphql_query(session, query, variables)
    if not data:
        return None
        
    try:
        blame_ranges = data['data']['repository']['object']['blame']['ranges']
        
        # Find the blame range containing our line
        for blame_range in blame_ranges:
            if blame_range['startingLine'] <= line <= blame_range['endingLine']:
                commit = blame_range['commit']
                return {
                    "author": commit['author']['name'],
                    "email": commit['author']['email'],
                    "date": commit['authoredDate'],
                    "message": commit['message'].split('\n')[0]  # First line only
                }
        
        return None
        
    except Exception as e:
        print(f"Error parsing blame info for {path}:{line}: {e}")
        return None

def get_recent_branch_data(repo: str, since_date: datetime, session: requests.Session) -> List[Dict]:
    """Get data for all branches with activity since given date.
    
    Returns a list of branch data dictionaries, each containing:
    - name: branch name
    - target: dict with:
      - history.nodes: list of commit data since since_date
      - oid: head commit SHA
      - committedDate: ISO date string of head commit
    """
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
                history(first: 100, since: $since) {
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
    
    all_pages = []
    cursor = None
    
    try:
        while True:
            variables = {
                "owner": owner,
                "name": repo_name,
                "since": since_date.isoformat(),
                "cursor": cursor
            }
            
            data = graphql_query(session, query, variables)
            if not data:
                break
                
            refs_data = data['data']['repository']['refs']
            all_pages.append(refs_data['nodes'])
            
            if not refs_data['pageInfo']['hasNextPage']:
                break
            cursor = refs_data['pageInfo']['endCursor']
        
        return [node for page in all_pages for node in page]  # Flatten pages
        
    except Exception as e:
        print(f"Error getting branch history for {repo}: {e}")
        return []

# Branch operations

def get_affected_files_for_branch(repo: str, head_sha: str, cutoff_date: datetime, session: requests.Session) -> List[str]:
    """Get files affected in branch since cutoff date"""
    base_sha = get_commit_at_date(repo, head_sha, cutoff_date, session)
    if not base_sha:
        return []
    
    return get_modified_files(repo, base_sha, head_sha, session) 
