"""Shared utility functions for runners."""

import logging
from pathlib import Path

from git import Repo

logger = logging.getLogger(__name__)


def ensure_repo_is_prepared(
    remote_url: str,
    commit: str,
    lean_data: Path,
    lean_version: str,
) -> Path:
    """
    Ensure the repository is cloned and checked out at the specified commit.

    Creates a directory structure: {lean_data}/{repo_name}/{lean_version}/{commit}
    If the repository already exists at that path, uses the existing checkout.
    Otherwise, clones the repository and checks out the specified commit.

    Args:
        remote_url: Git repository URL
        commit: Git commit SHA to checkout
        lean_data: Base directory for repository storage
        lean_version: Lean version (used for directory organization)

    Returns:
        Path to the repository checkout directory
    """
    # Create a directory name from the remote URL
    repo_name = remote_url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    checkout_path = lean_data / repo_name / lean_version / commit
    if not checkout_path.exists():
        logger.info(f"Cloning {remote_url}")
        repo = Repo.clone_from(remote_url, checkout_path)
        logger.info(f"Checking out {repo_name} repo at commit {commit}")
        repo.git.checkout(commit)
    else:
        logger.info(
            f"Repo {repo_name} with version {lean_version} on commit {commit} already exists at {checkout_path}"
        )
        repo = Repo(checkout_path)

    return checkout_path
