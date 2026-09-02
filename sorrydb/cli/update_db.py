import logging
from functools import partial
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from sorrydb.database.build_database import local_lister, update_database

app = typer.Typer()


@app.command()
def update(
    database_path: Annotated[
        Path,
        typer.Option(
            help="Path to the database JSON file",
            show_default=False,
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
    ],
    lean_data_path: Annotated[
        Optional[Path],
        typer.Option(
            help="Directory to store Lean data (default: use temporary directory)",
            exists=True,
            file_okay=False,
            dir_okay=True,
        ),
    ] = None,
    stats_file_path: Annotated[
        Optional[Path],
        typer.Option(
            help="Path to write update statistics (JSON format)",
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
    ] = None,
    report_file_path: Annotated[
        Optional[Path],
        typer.Option(
            help="Path to write markdown update report",
            file_okay=True,
            dir_okay=False,
        ),
    ] = None,
    all_branches: Annotated[
        bool,
        typer.Option(
            "--all-branches/--default-branch-only",
            help=(
                "Crawl every branch head instead of only the default branch. "
                "Each extra head costs a full Lean build, so this is off by "
                "default. Equivalent to SORRYDB_ALL_BRANCHES in the nightly job."
            ),
        ),
    ] = False,
):
    """
    Update an existing SorryDB database.
    """
    logger = logging.getLogger(__name__)

    lister = partial(local_lister, all_branches=True) if all_branches else local_lister

    try:
        update_database(
            database_path=database_path,
            lean_data_path=lean_data_path,
            stats_file=stats_file_path,
            report_file=report_file_path,
            list_commits=lister,
        )
        return 0
    except Exception as e:
        logger.error(f"Error updating database: {e}")
        logger.exception(e)
        return 1
