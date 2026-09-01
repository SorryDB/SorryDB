"""Nightly SorryDB update.

Plain Python, meant to run as a Cloud Run job on a Cloud Scheduler cron:

1. clone or refresh the data repo over HTTPS
2. update the database, building each repo either locally or on MorphCloud
3. deduplicate the database
4. commit, tag the day, push
5. post the deduplicated sorries to the leaderboard API in chunks

Configuration comes from the environment:
    GITHUB_TOKEN            token used to push to the data repo
    MORPH_API_KEY           read by the MorphCloud extractor
    SORRYDB_API_URL         leaderboard API base URL, e.g. https://api.sorrydb.org
    SORRYDB_DATA_REPO_URL   HTTPS URL of the data repo
    SORRYDB_EXTRACTOR       "morph" (default) or "local"
    SORRYDB_DRY_RUN         set to skip the push and the API post
"""

import datetime
import json
import logging
import os
import sys
from pathlib import Path

import requests
from git import Repo

from sorrydb.database.build_database import local_extractor, update_database
from sorrydb.database.deduplicate_database import deduplicate_database
from sorrydb.utils.git_ops import prepare_repository

LOCAL_CLONE_PATH = Path("/tmp/sorrydb-data-checkout")
DATA_REPO_BRANCH = "master"
DEFAULT_DATA_REPO_URL = "https://github.com/SorryDB/sorrydb-data.git"

GIT_USER_NAME = "Austin Letson"
GIT_EMAIL = "waustinletson@gmail.com"

# The deduplicated payload is a few MB, so post it in chunks
POST_CHUNK_SIZE = 500
POST_TIMEOUT = 300

logger = logging.getLogger("nightly_update")


def get_extractor(name: str):
    if name == "local":
        return local_extractor
    if name == "morph":
        # imported lazily: it requires MORPH_API_KEY
        from sorrydb.runners.morphcloud_crawler import morphcloud_extractor

        return morphcloud_extractor
    raise ValueError(f"Unknown extractor '{name}'. Available: morph, local")


def commit_and_push(repo_path: Path, data_repo_url: str, token: str, dry_run: bool):
    """Commit the update, tag the day, and push both to the data repo."""
    repo = Repo(repo_path)

    with repo.config_writer() as cw:
        logger.info(f"Configuring git user: {GIT_USER_NAME} <{GIT_EMAIL}>")
        cw.set_value("user", "name", GIT_USER_NAME).release()
        cw.set_value("user", "email", GIT_EMAIL).release()

    if not repo.is_dirty(untracked_files=True):
        logger.info("No changes to commit.")
        return

    logger.info("Staging changes...")
    repo.git.add(A=True)

    current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_msg = f"Updating SorryDB at {current_time_str}"
    logger.info(f"Committing changes with message: '{commit_msg}'")
    repo.index.commit(commit_msg)

    tag_name = datetime.datetime.now().strftime("%Y-%m-%d")  # daily tag
    tag_message = f"Database update on {current_time_str}"
    logger.info(f"Creating/updating tag '{tag_name}' with message: '{tag_message}'")
    # Use force=True to update the tag if it already exists
    repo.create_tag(tag_name, message=tag_message, force=True)

    if dry_run:
        logger.info("Dry run: skipping push.")
        return

    # Set the authenticated URL only now, so the token never reaches the logs
    # written while cloning.
    repo.remotes.origin.set_url(
        data_repo_url.replace("https://", f"https://x-access-token:{token}@", 1)
    )

    logger.info("Pushing changes to origin...")
    repo.remotes.origin.push().raise_if_error()

    logger.info(f"Pushing tag '{tag_name}' to origin...")
    repo.remotes.origin.push(
        refspec=f"refs/tags/{tag_name}", force=True
    ).raise_if_error()

    logger.info("Successfully committed and pushed changes and tag.")


def post_sorries(sorries_path: Path, api_url: str, dry_run: bool):
    """Post the deduplicated sorries to the leaderboard API in chunks."""
    with open(sorries_path, "r", encoding="utf-8") as f:
        sorries = json.load(f)["sorries"]

    logger.info(f"Posting {len(sorries)} sorries to {api_url} in chunks")

    for start in range(0, len(sorries), POST_CHUNK_SIZE):
        chunk = sorries[start : start + POST_CHUNK_SIZE]
        if dry_run:
            logger.info(f"Dry run: skipping post of {len(chunk)} sorries")
            continue
        response = requests.post(
            f"{api_url.rstrip('/')}/sorries/", json=chunk, timeout=POST_TIMEOUT
        )
        response.raise_for_status()
        logger.info(f"Posted sorries {start} to {start + len(chunk)}")

    logger.info("Finished posting sorries")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("sorrydb").setLevel(logging.INFO)

    data_repo_url = os.environ.get("SORRYDB_DATA_REPO_URL", DEFAULT_DATA_REPO_URL)
    api_url = os.environ.get("SORRYDB_API_URL")
    extractor_name = os.environ.get("SORRYDB_EXTRACTOR", "morph")
    dry_run = bool(os.environ.get("SORRYDB_DRY_RUN"))

    extract = get_extractor(extractor_name)

    token = os.environ.get("GITHUB_TOKEN")
    if not token and not dry_run:
        raise ValueError("GITHUB_TOKEN is required to push to the data repo")

    logger.info(
        f"Starting nightly update of {data_repo_url} "
        f"with the {extractor_name} extractor (dry_run={dry_run})"
    )

    repo_path = prepare_repository(
        data_repo_url, DATA_REPO_BRANCH, None, LOCAL_CLONE_PATH
    )

    database_file = repo_path / "sorry_database.json"
    deduplicated_file = repo_path / "deduplicated_sorries.json"

    update_database(
        database_path=database_file,
        lean_data_path=None,  # uses a temporary directory for Lean data
        stats_file=repo_path / "update_database_stats.json",
        report_file=repo_path / "update_report.md",
        extract=extract,
    )

    deduplicate_database(
        database_path=database_file, query_results_path=deduplicated_file
    )

    commit_and_push(repo_path, data_repo_url, token, dry_run)

    if api_url:
        post_sorries(deduplicated_file, api_url, dry_run)
    else:
        logger.info("SORRYDB_API_URL is not set, skipping the leaderboard post")

    logger.info("Nightly update finished.")


if __name__ == "__main__":
    sys.exit(main())
