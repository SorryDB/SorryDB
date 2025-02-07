from pathlib import Path
import shutil
from git import Repo
from typing import Optional
import tempfile

def get_head_sha(repository: str, branch: str = None) -> str:
    """Get the HEAD SHA of a branch."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo = Repo.clone_from(
            f"https://github.com/{repository}",
            temp_dir,
            branch=branch,
            depth=1
        )
        return repo.head.commit.hexsha

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
    if head_sha is None:
        head_sha = get_head_sha(repository, branch)
    
    checkout_path = lean_data / head_sha
    
    # If directory exists and has correct commit checked out, we're done
    if checkout_path.exists():
        try:
            repo = Repo(checkout_path)
            if repo.head.commit.hexsha == head_sha:
                print(f"Repository already exists at correct commit {head_sha}")
                return checkout_path
        except Exception:
            pass
    
    # Clean up if directory exists but wrong commit
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