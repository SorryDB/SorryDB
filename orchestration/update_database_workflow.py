import datetime
import logging  # Keep for potential direct logging configuration if needed
from pathlib import Path

from git import Repo
from prefect import flow, get_run_logger, task

from sorrydb.database.build_database import update_database
from sorrydb.database.deduplicate_database import deduplicate_database
from sorrydb.utils.git_ops import prepare_repository

# --- Configuration ---
DEFAULT_DATA_REPO_URL = "git@github.com:austinletson/sorrydb-data-test-mock-only.git"
# Local path where the data repository will be cloned.
DEFAULT_LOCAL_CLONE_PATH = "/tmp/sorrydb-data-checkout"
DEFAULT_DATA_REPO_BRANCH = "master"


@task
def setup_local_repo_task(repo_url: str, local_path_str: str, branch: str) -> Path:
    """
    Clones or updates a local copy of the data repository.
    Returns the path to the local repository.
    """
    logger = get_run_logger()
    local_path = Path(local_path_str).resolve()  # Use absolute path

    checkout_path = prepare_repository(
        repo_url, branch, head_sha=None, lean_data=local_path
    )

    if not checkout_path:
        logger.error("Failed to checkout repo")
        raise Exception("Failed to checkout repo")

    return checkout_path


@task
def run_update_database_task(repo_path: Path):
    """
    Runs the database update process.
    """
    logger = get_run_logger()
    logger.info("Starting database update...")

    database_file = repo_path / "sorry_database.json"
    stats_file = repo_path / "update_database_stats.json"

    update_database(
        database_path=database_file,
        lean_data_path=None,  # Uses a temporary directory for Lean data
        stats_file=stats_file,
    )
    logger.info(f"Database update complete. Stats written to {stats_file}")


@task
def run_deduplicate_database_task(repo_path: Path):
    """
    Runs the database deduplication process.
    """
    logger = get_run_logger()
    logger.info("Starting database deduplication...")

    database_file = repo_path / "sorry_database.json"
    results_file = repo_path / "deduplicated_sorries.json"

    deduplicate_database(database_path=database_file, query_results_path=results_file)
    logger.info(f"Database deduplication complete. Results written to {results_file}")


@task
def commit_and_push_changes_task(
    repo_path: Path, commit_message_prefix: str = "Prefect: Updating SorryDB"
):
    """
    Commits changes, tags, and pushes to the data repository.
    """
    logger = get_run_logger()
    repo = Repo(repo_path)

    if not repo.is_dirty(untracked_files=True):
        logger.info("No changes to commit.")
        return

    logger.info("Staging changes...")
    repo.git.add(A=True)

    current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_msg = f"{commit_message_prefix} at {current_time_str}"

    logger.info(f"Committing changes with message: '{commit_msg}'")
    repo.index.commit(commit_msg)

    tag_date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    tag_name = tag_date_str  # Daily tag
    tag_message = f"Database update on {current_time_str}"

    logger.info(f"Creating/updating tag '{tag_name}' with message: '{tag_message}'")
    # Use force=True to update the tag if it already exists (common for daily tags)
    # The original script would fail if the tag exists. Change force=False to match that.
    repo.create_tag(tag_name, message=tag_message, force=True)

    logger.info("Pushing changes to origin...")
    repo.remotes.origin.push()

    logger.info(f"Pushing tag '{tag_name}' to origin...")
    # Force push the tag if it was updated locally.
    # Use `refs/tags/{tag_name}` to specify the tag.
    repo.remotes.origin.push(refspec=f"refs/tags/{tag_name}", force=True)

    logger.info("Successfully committed and pushed changes and tag.")


@flow(name="Update SorryDB Data Workflow")
def update_sorrydb_data_flow(
    data_repo_url: str = DEFAULT_DATA_REPO_URL,
    local_clone_path_str: str = DEFAULT_LOCAL_CLONE_PATH,
    data_repo_branch: str = DEFAULT_DATA_REPO_BRANCH,
):
    sdb_logger = logging.getLogger("sorrydb")
    sdb_logger.setLevel(logging.INFO)
    logger = get_run_logger()
    logger.info(
        f"Starting SorryDB data update workflow for repo: {data_repo_url}, branch: {data_repo_branch}"
    )

    repo_fs_path = setup_local_repo_task(
        repo_url=data_repo_url,
        local_path_str=local_clone_path_str,
        branch=data_repo_branch,
    )

    run_update_database_task(repo_path=repo_fs_path)

    run_deduplicate_database_task(repo_path=repo_fs_path)

    commit_and_push_changes_task(repo_path=repo_fs_path)

    logger.info("SorryDB data update workflow finished.")


def main_run():
    """
    Entry point for running the flow via a Poetry script.
    Uses default parameters defined in this file.
    """
    # Ensure PREFECT_API_URL is set if using a server/cloud, or runs locally.
    update_sorrydb_data_flow(
        data_repo_url=DEFAULT_DATA_REPO_URL,
        local_clone_path_str=DEFAULT_LOCAL_CLONE_PATH,
        data_repo_branch=DEFAULT_DATA_REPO_BRANCH,
    )
