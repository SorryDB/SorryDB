from typing import List, Dict, Any
from datetime import datetime
import requests

from github_api import (
    get_file_content,
    get_blame_info,
    get_affected_files_for_branch
)

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