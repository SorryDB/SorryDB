import json
import logging
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from sorrydb.database.sorry import Sorry

logger = logging.getLogger(__name__)


class JsonDatabase:
    def __init__(self):
        self.data = None
        self.update_stats = defaultdict(
            lambda: defaultdict(lambda: {"count": 0, "count_new": 0})
        )

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

    def add_sorry(self, sorry: Sorry):
        sorry_dict = asdict(sorry)
        self.data["sorries"].append(sorry_dict)

        repo_url = sorry.repo.remote
        commit_sha = sorry.repo.commit

        is_new_goal = False
        current_goal = sorry.debug_info.goal if sorry.debug_info else None
        if current_goal:
            is_new_goal = all(
                existing_sorry.get("debug_info", {}).get("goal") != current_goal
                for existing_sorry in self.data["sorries"][:-1]
            )

        repo_stats = self.update_stats[repo_url][commit_sha]
        repo_stats["count"] += 1
        if is_new_goal:
            repo_stats["count_new"] += 1

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

    def write_stats(self, write_stats_path: Path):
        logger.info(f"Writing database update stats to {write_stats_path}")
        with open(write_stats_path, "w") as f:
            json.dump(
                self.update_stats,
                f,
                indent=2,
            )
        logger.info("Database stats written successfully")
