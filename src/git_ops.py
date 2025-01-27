from pathlib import Path
import shutil
from git import Repo
from typing import Optional

def prepare_repository(repository: str, branch: str, head_sha: str, lean_data: Path) -> Optional[Path]:
    """Clone repository at specific commit into lean-data directory.
    
    Args:
        repository: Repository name (owner/repo)
        branch: Branch name
        head_sha: Commit SHA to checkout
        lean_data: Base directory for checkouts
    
    Returns:
        Path to checked out repository or None if failed
    """
    checkout_path = lean_data / head_sha
    
    # Clean up if directory exists
    if checkout_path.exists():
        shutil.rmtree(checkout_path)
    
    try:
        # Clone repository
        repo_url = f"https://github.com/{repository}"
        print(f"Cloning {repo_url} branch {branch}...")
        repo = Repo.clone_from(
            repo_url,
            checkout_path,
            branch=branch,
            single_branch=True
        )
        
        # Checkout specific commit
        print(f"Checking out {head_sha}...")
        repo.git.checkout(head_sha)
        
        return checkout_path
        
    except Exception as e:
        print(f"Error preparing repository: {e}")
        # Clean up on failure
        if checkout_path.exists():
            shutil.rmtree(checkout_path)
        return None 