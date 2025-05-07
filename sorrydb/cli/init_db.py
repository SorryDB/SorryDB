import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from sorrydb.database.build_database import init_database

app = typer.Typer()


@app.command()
def init(
    repos_path: Annotated[
        Path,
        typer.Option(
            help="JSON file containing list of repositories to process",
            show_default=False,
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
    ],
    database_path: Annotated[
        Path,
        typer.Option(
            help="Output file path for the database",
            show_default=False,
        ),
    ],
    starting_date: Annotated[
        Optional[datetime],
        typer.Option(
            help="Starting date for all repositories",
            show_default="Today's date",
        ),
    ] = None,
):
    """
    Initialize a SorryDB database from repositories.
    """
    """Execute the init database logic."""
    logger = logging.getLogger(__name__)

    # Parse the starting date if provided
    if starting_date:
        # Parse as YYYY-MM-DD format and make timezone-aware (UTC)
        # TODO: this might should use local timezone
        starting_date = starting_date.replace(tzinfo=timezone.utc)
        logger.info(f"Using starting date: {starting_date.isoformat()}")
    else:
        # Use current date and time if not provided (with UTC timezone)
        starting_date = datetime.now(timezone.utc)
        logger.info(
            f"No starting date provided, using current date and time: {starting_date.isoformat()}"
        )

    with open(repos_path, "r") as f:
        repos_data = json.load(f)

    repos_list = [repo["remote"] for repo in repos_data["repos"]]

    try:
        init_database(
            repo_list=repos_list,
            starting_date=starting_date,
            database_file=database_path,
        )
    except Exception as e:
        logger.error(f"Error building database: {e}")
        logger.exception(e)
        return 1

    return 0
