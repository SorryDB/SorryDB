import logging
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from sorrydb.database.deduplicate_database import deduplicate_database

app = typer.Typer()


@app.command()
def deduplicate(
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
    query_results_path: Annotated[
        Optional[Path],
        typer.Option(
            help="Path to write query results (JSON format)",
            show_default="Write results to stdout",
            file_okay=True,
            dir_okay=False,
        ),
    ] = None,
):
    """
    Deduplicate the sorries in a SorryDB database.
    """
    logger = logging.getLogger(__name__)

    try:
        deduplicate_database(
            database_path=database_path, query_results_path=query_results_path
        )
        return 0
    except Exception as e:
        logger.error(f"Error deduplicating database: {e}")
        logger.exception(e)
        return 1
