import json
import logging
from dataclasses import asdict
from pathlib import Path

from sorrydb.database.sorry import Sorry

logger = logging.getLogger(__name__)


class JsonDatabase:
    def __init__(self):
        self.data = None

    def load_database(self, database_path):
        """
        Load a SorryDatabase from a JSON file.

        Raises:
            FileNotFoundError: If the database file doesn't exist
            ValueError: If the database file contains invalid JSON
        """
        logger.info(f"Loading sorry database from {database_path}")

        try:
            with open(database_path, "r") as f:
                database = json.load(f)
            self.data = database
        except FileNotFoundError:
            logger.error(f"Database file not found: {database_path}")
            raise FileNotFoundError(f"Database file not found: {database_path}")
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in database file: {database_path}")
            raise ValueError(f"Invalid JSON in database file: {database_path}")

    def get_all_repos(self):
        return self.data["repos"]

    def add_sorries(self, sorries: list[Sorry]):
        sorries_dict = map(asdict, sorries)
        self.data["sorries"].extend(sorries_dict)

    def write_database(self, write_database_path: Path):
        logger.info(f"Writing updated database to {write_database_path}")
        with open(write_database_path, "w") as f:
            json.dump(
                self.data,
                f,
                indent=2,
                default=Sorry.default_json_serialization,
            )
        logger.info("Database update completed successfully")
