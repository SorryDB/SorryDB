#!/usr/bin/env python3

import json
import logging
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from sorrydb.utils.extract_sorry import extract_sorries_from_repo

app = typer.Typer()

logger = logging.getLogger(__name__)


@app.command()
def extract(
    repo_path: Annotated[
        Path,
        typer.Option(
            help="Path to the Lean repository to extract sorries from",
            show_default=False,
            exists=True,
            file_okay=False,
            dir_okay=True,
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
):
    """
    Extract sorries from a Lean repository using ExtractSorry.lean script.
    
    This command uses the ExtractSorry.lean script via elan to extract sorry
    statements from Lean files, which is different from the REPL-based extraction
    used by the 'update' command.
    """
    logger.info(f"Extracting sorries from repository: {repo_path}")
    
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
        output_data = {
            "repository": {
                "path": str(repo_path),
                "lean_version": lean_version,
            },
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