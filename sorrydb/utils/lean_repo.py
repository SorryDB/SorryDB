#!/usr/bin/env python3

import logging
import subprocess
from pathlib import Path

# Create a module-level logger
logger = logging.getLogger(__name__)


def build_lean_project(repo_path: Path):
    """
    Run lake commands to build the Lean project.

    Args:
        repo_path: Path to the Lean project.
    """
    # Check if the project uses mathlib4
    use_cache = False
    manifest_path = repo_path / "lake-manifest.json"
    if manifest_path.exists():
        try:
            manifest_content = manifest_path.read_text()
            if "https://github.com/leanprover-community/mathlib4" in manifest_content:
                use_cache = True
                logger.info("Project uses mathlib4, will get build cache")
            elif '"name": "mathlib"' in manifest_content:
                use_cache = True
                logger.info(
                    "Project appears to be mathlib4 branch, will get build cache"
                )
        except Exception as e:
            logger.warning(f"Could not read lake-manifest.json: {e}")

    # Only get build cache if the project uses mathlib4
    if use_cache:
        logger.info("Getting build cache...")
        result = subprocess.run(["lake", "exe", "cache", "get"], cwd=repo_path)
        if result.returncode != 0:
            logger.warning("lake exe cache get failed, continuing anyway")
    else:
        logger.info("Project does not use mathlib4, skipping build cache step")

    logger.info("Building project...")
    result = subprocess.run(["lake", "build"], cwd=repo_path)
    if result.returncode != 0:
        logger.error("lake build failed")
        raise Exception("lake build failed")
