import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from sorrydb.database.sorry import Sorry, SorryJSONEncoder, sorry_object_hook

logger = logging.getLogger(__name__)


class JsonDatabase:
    def __init__(self):
        self.sorries: list[Sorry] = []
        self.repos = None
        self.update_stats = defaultdict(
            lambda: {
                "counts": defaultdict(
                    lambda: {
                        "count": 0,
                        "count_new_goal": 0,
                        # Sorries kept even though the REPL could not confirm
                        # their goal is Prop valued
                        "undetermined_type": 0,
                    }
                ),
                "new_leaf_commit": None,
                "start_processing_time": None,
                "end_processing_time": None,
                "lake_timeout": None,
                "lean_version": None,
            }
        )

    def set_new_leaf_commit(self, repo_url, new_leaf_commit):
        self.update_stats[repo_url]["new_leaf_commit"] = new_leaf_commit

    def set_start_processing_time(self, repo_url, start_processing_time):
        self.update_stats[repo_url]["start_processing_time"] = start_processing_time

    def set_end_processing_time(self, repo_url, end_processing_time):
        self.update_stats[repo_url]["end_processing_time"] = end_processing_time

    def set_lake_timeout(self, repo_url, lake_timeout):
        self.update_stats[repo_url]["lake_timeout"] = lake_timeout

    def set_lean_version(self, repo_url, lean_version):
        """Record the Lean version a repo was extracted with.

        Reported alongside the undetermined type count, since the REPL's ability
        to answer the parent type query is version dependent.
        """
        self.update_stats[repo_url]["lean_version"] = lean_version

    def add_undetermined_type(self, repo_url, commit_sha):
        """Count a sorry that was included without confirming its goal is Prop."""
        self.update_stats[repo_url]["counts"][commit_sha]["undetermined_type"] += 1

    def set_unsupported_toolchain(self, repo_url, reason):
        """Record why a repo was skipped without being attempted.

        Deliberately not part of the default stats shape, so the stats of a repo
        that was attempted normally are unchanged.
        """
        self.update_stats[repo_url]["unsupported_toolchain"] = reason

    def load_database(self, database_path):
        """
        Load a SorryDatabase from a JSON file.

        Raises:
            FileNotFoundError: If the database file doesn't exist
            ValueError: If the database file contains invalid JSON
        """
        logger.info(f"Loading sorry database from {database_path}")

        with open(database_path, "r", encoding="utf-8") as f:
            # use sorry_object_hook to automatically create Sorry instances
            database_dict = json.load(f, object_hook=sorry_object_hook)

        self.repos = database_dict["repos"]
        self.sorries = database_dict["sorries"]

    def get_all_repos(self):
        return self.repos

    def get_sorries(self) -> list[Sorry]:
        return self.sorries

    def add_sorry(self, sorry: Sorry):
        self.sorries.append(sorry)

        repo_url = sorry.repo.remote
        commit_sha = sorry.repo.commit

        is_new_goal = False
        current_goal = sorry.debug_info.goal if sorry.debug_info else None
        if current_goal:
            is_new_goal = all(
                existing_sorry.debug_info.goal != current_goal
                for existing_sorry in self.sorries[:-1]
            )

        repo_stats = self.update_stats[repo_url]["counts"][commit_sha]
        repo_stats["count"] += 1
        if is_new_goal:
            repo_stats["count_new_goal"] += 1

    def write_database(self, write_database_path: Path):
        logger.info(f"Writing updated database to {write_database_path}")

        database_dict = {"repos": self.repos, "sorries": self.sorries}

        with open(write_database_path, "w", encoding="utf-8") as f:
            json.dump(
                database_dict, f, indent=2, cls=SorryJSONEncoder, ensure_ascii=False
            )
        logger.info("Database update completed successfully")

    def write_stats(self, write_stats_path: Path):
        logger.info(f"Writing database update stats to {write_stats_path}")
        with open(write_stats_path, "w", encoding="utf-8") as f:
            json.dump(
                self.update_stats,
                f,
                indent=2,
            )
        logger.info("Database stats written successfully")

    def aggregate_update_stats(self) -> tuple:
        """
        Uses self.update_stats to calculate aggregate update stats:
        - total number of repos with new commits
        - total number of repos with a lake timeout
        - total number of sorries
        - total number of new sorries
        - total number of sorries kept without a confirmed Prop type
        """
        repos_with_new_commits = 0
        repos_with_lake_timeout = 0
        total_sorries_count = 0
        total_new_goal_sorries_count = 0
        total_undetermined_type_count = 0

        for stats in self.update_stats.values():
            if stats["new_leaf_commit"] is not None:
                repos_with_new_commits += 1

            if stats["lake_timeout"] is True:
                repos_with_lake_timeout += 1

            for commit_stats in stats["counts"].values():
                total_sorries_count += commit_stats["count"]
                total_new_goal_sorries_count += commit_stats["count_new_goal"]
                total_undetermined_type_count += commit_stats.get(
                    "undetermined_type", 0
                )

        return (
            repos_with_new_commits,
            repos_with_lake_timeout,
            total_sorries_count,
            total_new_goal_sorries_count,
            total_undetermined_type_count,
        )

    @staticmethod
    def _calculate_human_readable_processing_time(
        start_time_iso: str, end_time_iso: str
    ) -> str:
        start_dt = datetime.fromisoformat(start_time_iso)
        end_dt = datetime.fromisoformat(end_time_iso)

        total_seconds = (end_dt - start_dt).total_seconds()

        hours, remainder = divmod(int(total_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def write_stats_report(self, report_path: Path):
        """
        Aggregates update stats and writes a markdown based report to the `report_path`
        """
        (
            repos_with_new_commits,
            repos_with_lake_timeout,
            total_sorries_count,
            total_new_goal_sorries_count,
            total_undetermined_type_count,
        ) = self.aggregate_update_stats()

        unsupported = {
            repo_url: stats["unsupported_toolchain"]
            for repo_url, stats in self.update_stats.items()
            if stats.get("unsupported_toolchain")
        }

        report_content = f"""# SorryDB Update Stats report

## Summary

- **Repositories with new commits:** {repos_with_new_commits}
- **Repositories with lake timeout:** {repos_with_lake_timeout}
- **Repositories skipped for unsupported toolchain:** {len(unsupported)}
- **Total sorries found:** {total_sorries_count}
- **Total new goal sorries found:** {total_new_goal_sorries_count}
- **Sorries included with undetermined type:** {total_undetermined_type_count}
- **Total number of sorries after update:** {len(self.sorries)}

The database documents its sorries as Prop valued. The REPL cannot always
answer that question, and a sorry whose type could not be determined is
included rather than dropped, because dropping silently emptied whole
repositories. The count above is how many were included unverified; if it is
concentrated in particular Lean versions, the fix belongs in the REPL
interaction rather than in the filter.

## Detailed Stats per Repository with new commits

| Repository URL | Lean Version | Lake Timeout | Processing Time | Sorries | New Goal Sorries | Undetermined Type |
|----------------|--------------|--------------|-----------------|---------|------------------|-------------------|
"""

        for repo_url, stats in self.update_stats.items():
            # Don't add repos with no new leaf commits to report
            if not stats["new_leaf_commit"]:
                continue

            lake_timeout_status = "Yes" if stats["lake_timeout"] else "No"
            processing_time = self._calculate_human_readable_processing_time(
                stats["start_processing_time"], stats["end_processing_time"]
            )

            repo_total_sorries = 0
            repo_total_new_goal_sorries = 0
            repo_total_undetermined_type = 0
            for commit_stats in stats["counts"].values():
                repo_total_sorries += commit_stats["count"]
                repo_total_new_goal_sorries += commit_stats["count_new_goal"]
                repo_total_undetermined_type += commit_stats.get(
                    "undetermined_type", 0
                )

            lean_version = stats.get("lean_version") or "unknown"

            report_content += (
                f"| {repo_url} | {lean_version} | {lake_timeout_status} "
                f"| {processing_time} | {repo_total_sorries} "
                f"| {repo_total_new_goal_sorries} | {repo_total_undetermined_type} |\n"
            )

        if unsupported:
            report_content += """
## Repositories skipped for unsupported toolchain

These were not attempted, so their watermarks are unchanged and they are
re-checked on the next update.

| Repository URL | Reason |
|----------------|--------|
"""
            for repo_url, reason in sorted(unsupported.items()):
                report_content += f"| {repo_url} | {reason} |\n"

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        logger.info(f"Stats report written successfully to {report_path}")
