import logging
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from sorrydb.cli.deduplicate_db import app as deduplicate_app
from sorrydb.cli.init_db import app as init_app
from sorrydb.cli.update_db import app as update_app

app = typer.Typer()

app.add_typer(deduplicate_app)
app.add_typer(init_app)
app.add_typer(update_app)


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# Common state or callback for global options like logging
@app.callback()
def main(
    log_level: Annotated[
        LogLevel, typer.Option(help="Set the logging level.")
    ] = LogLevel.INFO,
    log_file: Annotated[
        Optional[Path],
        typer.Option(
            help="Log file path",
            show_default="Write logs to stdout",
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
    ] = None,
):
    """
    SorryDB command-line interface.
    """
    # Configure logging based on common arguments
    log_kwargs = {
        "level": getattr(logging, log_level),
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    }
    if log_file:
        log_kwargs["filename"] = log_file
    logging.basicConfig(**log_kwargs)


if __name__ == "__main__":
    app()
