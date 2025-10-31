#!/usr/bin/env python3

import json
import logging
import tempfile
from pathlib import Path
from typing import Optional, Union

import typer
from typing_extensions import Annotated

from sorrydb.utils.extract_sorry import extract_sorries_from_repo
from sorrydb.utils.git_ops import prepare_repository

app = typer.Typer()

logger = logging.getLogger(__name__)


@app.command()
def extract(
    repo_source: Annotated[
        str,
        typer.Argument(
            help="Local path to Lean repository or git URL (e.g., https://github.com/user/repo.git)",
            show_default=False,
        ),
    ],
    output_file: Annotated[
        Optional[Path],
        typer.Option(
            help="Output JSON file path (default: print to stdout)",
            file_okay=True,
            dir_okay=False,
        ),
    ] = None,
    lean_version: Annotated[
        Optional[str],
        typer.Option(
            help="Lean version to use for extraction (e.g., 'v4.17.0'). If not provided, will try to detect from lean-toolchain file.",
        ),
    ] = None,
    filter_files: Annotated[
        Optional[str],
        typer.Option(
            help="Glob pattern to filter files (e.g., 'MyProject/**/*.lean')",
        ),
    ] = None,
    branch: Annotated[
        str,
        typer.Option(
            help="Branch to checkout for git URLs (default: main)",
        ),
    ] = "main",
    commit_sha: Annotated[
        Optional[str],
        typer.Option(
            help="Specific commit SHA to checkout (overrides branch)",
        ),
    ] = None,
    lean_data_dir: Annotated[
        Optional[Path],
        typer.Option(
            help="Directory to store cloned repositories (default: temporary directory)",
            file_okay=False,
            dir_okay=True,
        ),
    ] = None,
):
    """
    Extract sorries from a Lean repository using ExtractSorry.lean script.
    
    This command uses the ExtractSorry.lean script via elan to extract sorry
    statements from Lean files, which is different from the REPL-based extraction
    used by the 'update' command.
    
    Supports both local repository paths and git URLs. For git URLs, the repository
    will be cloned automatically.
    """
    logger.info(f"Extracting sorries from repository source: {repo_source}")
    
    # Determine if repo_source is a URL or local path
    is_git_url = repo_source.startswith(('http://', 'https://', 'git@', 'ssh://'))
    
    if is_git_url:
        # Handle git URL - clone the repository
        if lean_data_dir:
            lean_data_path = lean_data_dir
        else:
            # Create temporary directory for cloning
            temp_dir = tempfile.mkdtemp(prefix="sorrydb_extract_")
            lean_data_path = Path(temp_dir)
            logger.info(f"Using temporary directory for git clone: {lean_data_path}")
        
        logger.info(f"Cloning git repository: {repo_source}")
        repo_path = prepare_repository(
            remote_url=repo_source,
            branch=branch,
            head_sha=commit_sha,
            lean_data=lean_data_path,
        )
        logger.info(f"Repository cloned to: {repo_path}")
    else:
        # Handle local path
        repo_path = Path(repo_source)
        if not repo_path.exists():
            logger.error(f"Local repository path does not exist: {repo_path}")
            return 1
        if not repo_path.is_dir():
            logger.error(f"Repository path is not a directory: {repo_path}")
            return 1
    
    # Auto-detect Lean version if not provided
    if not lean_version:
        toolchain_file = repo_path / "lean-toolchain"
        if toolchain_file.exists():
            try:
                toolchain_content = toolchain_file.read_text().strip()
                if ":" in toolchain_content:
                    lean_version = toolchain_content.split(":", 1)[1]
                    logger.info(f"Detected Lean version: {lean_version}")
                else:
                    logger.warning(f"Unexpected lean-toolchain format: {toolchain_content}")
                    lean_version = "default"
            except Exception as e:
                logger.warning(f"Could not read lean-toolchain file: {e}")
                lean_version = "default"
        else:
            logger.warning("No lean-toolchain file found, using default version")
            lean_version = "default"
    
    # Create file filter if provided
    file_filter = None
    if filter_files:
        import fnmatch
        def filter_fn(file_path: Path) -> bool:
            return fnmatch.fnmatch(str(file_path), filter_files)
        file_filter = filter_fn
    
    try:
        # Extract sorries using ExtractSorry.lean
        sorries = extract_sorries_from_repo(
            repo_path=repo_path,
            lean_version=lean_version,
            file_filter=file_filter
        )
        
        # Prepare output data
        repo_info = {
            "path": str(repo_path),
            "lean_version": lean_version,
        }
        
        # Add git metadata if this was a git URL
        if is_git_url:
            from sorrydb.utils.git_ops import get_repo_metadata
            try:
                git_metadata = get_repo_metadata(repo_path)
                repo_info.update({
                    "source_url": repo_source,
                    "branch": branch,
                    "commit_sha": commit_sha,
                    "git_metadata": git_metadata,
                })
            except Exception as e:
                logger.warning(f"Could not get git metadata: {e}")
                repo_info["source_url"] = repo_source
        
        output_data = {
            "repository": repo_info,
            "extraction_method": "ExtractSorry.lean",
            "sorries_count": len(sorries),
            "sorries": sorries,
        }
        
        # Output results
        if output_file:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Wrote {len(sorries)} sorries to {output_file}")
        else:
            # Print to stdout
            print(json.dumps(output_data, indent=2, ensure_ascii=False))
        
        logger.info(f"Successfully extracted {len(sorries)} sorries")
        return 0
        
    except Exception as e:
        logger.error(f"Error extracting sorries: {e}")
        logger.exception(e)
        return 1


if __name__ == "__main__":
    app()