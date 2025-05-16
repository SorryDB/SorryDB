import logging
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from sorrydb.cli.deduplicate_db import app as deduplicate_app
from sorrydb.cli.init_db import app as init_app
from sorrydb.cli.settings import LogLevel, SorryDBSettings
from sorrydb.cli.update_db import app as update_app

app = typer.Typer()

app.add_typer(deduplicate_app)
app.add_typer(init_app)
app.add_typer(update_app)

settings = SorryDBSettings()


# Common state or callback for global options like logging
@app.callback()
def main(
    log_level: Annotated[
        LogLevel, typer.Option(help="Set the logging level.")
    ] = settings.log_level,
    log_file: Annotated[
        Optional[Path],
        typer.Option(
            help="Log file path",
            show_default="Write logs to stdout",
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
    ] = settings.log_file,
):
    """
    SorryDB command-line interface.
    """
    # Configure logging based on common arguments
    print(log_level)
    log_kwargs = {
        "level": getattr(logging, log_level),
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    }
    if log_file:
        log_kwargs["filename"] = log_file
    logging.basicConfig(**log_kwargs)


if __name__ == "__main__":
    app()
