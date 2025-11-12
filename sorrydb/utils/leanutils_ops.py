import logging
import subprocess
from pathlib import Path
from typing import List, Tuple

from git import Repo

logger = logging.getLogger(__name__)

LEANUTILS_REPO_URL = "https://github.com/SorryDB/LeanUtils"

def leanutils_release_tag(version_tag: str) -> str:
    """Given the version_tag of a Lean repo, determine which 
    release tag for SorryDB/LeanUtils to use for extraction purposes
    """
    
    # for now, use the main branch which works for everything in the 4.9.0 to 4.25.0-rc1 interval.
    # at some point, may need to determine the most recent release tag which is \leq version_string
    return "main"

def setup_leanutils(lean_data: Path, version_tag: str) -> Path:
    """Clone and build the relevant release of SorryDB/LeanUtils. If the
    directory corresponding to the version tag already exists, it is assumed to
    contain a built lean extractor binary already.

    TODO: at later stage return a dict with various binaries (for sorry extraction and other functionality)

    Args:
        lean_data: Path where SorryDB/LeanUtils should be cloned
        version_tag: version tag of the Lean repository

    Returns:
        Path to the ExtractSorry binary
    """
    # Determine the relevant release tag, and create directory name including the release tag
    release_tag = leanutils_release_tag(version_tag)
    sanitized_tag = release_tag.replace(".", "_").replace("-", "_")
    leanutils_dir = lean_data / f"leanutils_{sanitized_tag}"

    if not leanutils_dir.exists():
        logger.info(f"Cloning SorryDB/LeanUtils repository into {leanutils_dir}...")
        repo = Repo.clone_from(LEANUTILS_REPO_URL, leanutils_dir)

        logger.info(f"Checking out SorryDB/LeanUtils at tag: {release_tag}")
        repo.git.checkout(release_tag)

        logger.info("Building LeanUtils...")
        result = subprocess.run(["lake", "build"], cwd=leanutils_dir)

        if result.returncode != 0:
            raise RuntimeError(
                "Failed to build LeanUtils. Lake build returned: %s", result.stderr
            )

    sorryextractor_binary = leanutils_dir / "bins" / "ExtractSorry.lean"
    if not sorryextractor_binary.exists():
        raise FileNotFoundError(f"SorryExtractor binary not found at {sorryextractor_binary}")

    # Make binary executable
    sorryextractor_binary.chmod(0o755)
    logger.info("ExtractSorry binary ready at %s", sorryextractor_binary)

    return sorryextractor_binary

