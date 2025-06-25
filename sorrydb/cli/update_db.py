import logging
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from sorrydb.database.build_database import update_database

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
            file_okay=True,
            dir_okay=False,
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
):
    """
    Update an existing SorryDB database.
    """
    logger = logging.getLogger(__name__)

    try:
        update_database(
            database_path=database_path,
            lean_data_path=lean_data_path,
            stats_file=stats_file_path,
            report_file=report_file_path,
        )
        return 0
    except Exception as e:
        logger.error(f"Error updating database: {e}")
        logger.exception(e)
        return 1
