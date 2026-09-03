"""Nightly SorryDB update.

Plain Python, meant to run as a Cloud Run job on a Cloud Scheduler cron. It has
two modes, selected with SORRYDB_MODE, and the default runs both in order:

crawl
    Update sorry_database.json in place at SORRYDB_DATABASE_PATH, checkpointing
    after every repo. No git, no push. On Cloud Run the path is a mounted GCS
    bucket, so from here it is just a local path and needs no GCS client.

    With the morph extractor this runs in two passes: pass one lists every
    repo's new leaf commits (one ls-remote plus one shallow clone per repo, done
    exactly once), then all extractions fan out across MorphCloud VMs in
    parallel, then pass two replays the prefetched results through the ordinary
    crawl loop.

publish
    Clone the data repo, copy the database plus stats and report into it,
    deduplicate, commit, tag the day, push, then post the deduplicated sorries
    to the leaderboard API. Runnable on its own, so a crawl that died can still
    be published later.

Configuration comes from the environment:
    SORRYDB_MODE            "all" (default), "crawl" or "publish"
    SORRYDB_DATABASE_PATH   database to crawl and publish, default /data/sorry_database.json
    SORRYDB_EXTRACTOR       "morph" (default) or "local"
    SORRYDB_ALL_BRANCHES    set to crawl every branch head, not just the default branch
    SORRYDB_MORPH_WORKERS   concurrent MorphCloud VMs, default 8
    SORRYDB_COMMIT          SorryDB commit the MorphCloud VMs check out
    MORPH_API_KEY           read by the MorphCloud extractor
    SORRYDB_DATA_REPO_URL   HTTPS URL of the data repo
    GITHUB_TOKEN            token used to push to the data repo
    SORRYDB_API_URL         leaderboard API base URL, e.g. https://api.sorrydb.org
    SORRYDB_DRY_RUN         set to skip the push and the API post
"""

import datetime
import json
import logging
import os
import shutil
import sys
from functools import partial
from pathlib import Path

import requests
from git import Repo

from sorrydb.database.build_database import (
    cached_extractor,
    cached_lister,
    listings_to_work,
    local_lister,
    unsupported_toolchain_repos,
    update_database,
)
from sorrydb.database.deduplicate_database import deduplicate_database
from sorrydb.database.sorry_database import JsonDatabase
from sorrydb.utils.git_ops import default_branch_head, prepare_repository

DEFAULT_DATABASE_PATH = "/data/sorry_database.json"
LOCAL_CLONE_PATH = Path("/tmp/sorrydb-data-checkout")
DEFAULT_DATA_REPO_URL = "https://github.com/SorryDB/sorrydb-data.git"

GIT_USER_NAME = "Austin Letson"
GIT_EMAIL = "waustinletson@gmail.com"

# The deduplicated payload is a few MB, so post it in chunks
POST_CHUNK_SIZE = 500
POST_TIMEOUT = 300

MODES = ("all", "crawl", "publish")
EXTRACTORS = ("morph", "local")

logger = logging.getLogger("nightly_update")


def list_new_commits(repos, lister, unsupported: dict) -> dict:
    """Pass one: list each supported repo's new leaf commits.

    This is the only sequential network work of a crawl, and it happens exactly
    once per run. Repos with an unsupported toolchain are left out entirely, so
    they cost neither a listing nor a VM. Returns {repo_url: lister result},
    which cached_lister replays in pass two.
    """
    return {
        repo["remote_url"]: lister(repo)
        for repo in repos
        if repo["remote_url"] not in unsupported
    }


def crawl(database_path: Path, extractor_name: str, all_branches: bool):
    """Update the database in place, checkpointing after every repo."""
    logger.info(
        f"Crawling {database_path} with the {extractor_name} extractor "
        f"(all_branches={all_branches})"
    )

    # Every branch head costs its own VM and its own full Lean build, and the
    # dedup step then collapses most of those sorries because branches of one
    # repo largely share goals. So only the default branch is crawled unless
    # asked otherwise.
    lister = partial(local_lister, all_branches=True) if all_branches else local_lister

    database = JsonDatabase()
    database.load_database(database_path)
    repos = database.get_all_repos()

    # Resolve toolchains before anything expensive: a repo the REPL cannot
    # handle would otherwise fail extraction after we had paid for the build.
    unsupported = unsupported_toolchain_repos([r["remote_url"] for r in repos])
    logger.info(
        f"{len(unsupported)} of {len(repos)} repos skipped for unsupported toolchain"
    )
    for repo_url, reason in sorted(unsupported.items()):
        logger.info(f"Unsupported toolchain, skipping {repo_url}: {reason}")

    # Refresh stars and last activity from the GitHub API before deciding who
    # is eligible. Roughly one GraphQL call per 100 repos, and it fails open:
    # a failure leaves the stored metadata standing rather than marking the
    # whole index ineligible.
    from sorrydb.database.github_index import fetch_repo_metadata

    update_args = {
        "database_path": database_path,
        "fetch_metadata": fetch_repo_metadata,
        "lean_data_path": None,  # uses a temporary directory for Lean data
        "stats_file": database_path.parent / "update_database_stats.json",
        "report_file": database_path.parent / "update_report.md",
        "unsupported_toolchains": unsupported,
    }

    if extractor_name == "local":
        update_database(**update_args, list_commits=lister)
        return

    # imported lazily: it requires MORPH_API_KEY
    from sorrydb.runners.morphcloud_crawler import (
        prefetch,
        sweep_orphaned_instances,
    )

    # Stop any VM a previous run leaked before starting more, and again on the
    # way out however we leave.
    sweep_orphaned_instances()
    try:
        listings = list_new_commits(repos, lister, unsupported)
        work = listings_to_work(listings)
        logger.info(f"Listed {len(work)} new commits across {len(listings)} repos")

        cache = prefetch(work)

        update_database(
            **update_args,
            extract=cached_extractor(cache),
            list_commits=cached_lister(listings),
        )
    finally:
        sweep_orphaned_instances()


def _push_url(data_repo_url: str, token: str) -> str:
    """The data repo URL with the push token attached.

    Fails loudly on a non-https URL rather than returning it unchanged, which
    used to surface later as an opaque authentication failure.
    """
    if not token:
        return data_repo_url
    if not data_repo_url.startswith("https://"):
        raise ValueError(
            f"The data repo URL must be https to attach a token: {data_repo_url}"
        )
    return data_repo_url.replace("https://", f"https://x-access-token:{token}@", 1)


def commit_and_push(
    repo_path: Path, data_repo_url: str, token: str, branch: str, dry_run: bool
):
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

    push_url = _push_url(data_repo_url, token)

    # Pushed by URL rather than by configuring the remote. A token written into
    # .git/config outlives the run, and any checkout that survives between runs
    # would reuse it, possibly after it has been rotated. GitPython redacts
    # credentials from GitCommandError, so a failure does not leak it either.
    # Explicit refspecs: a bare push would depend on push.default and on the
    # checkout's upstream, and pushing the wrong branch looks like success.
    logger.info(f"Pushing changes to origin {branch}...")
    repo.git.push(push_url, f"{branch}:{branch}")

    logger.info(f"Pushing tag '{tag_name}' to origin...")
    repo.git.push("--force", push_url, f"refs/tags/{tag_name}")

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


def publish(
    database_path: Path,
    data_repo_url: str,
    token: str,
    api_url: str,
    dry_run: bool,
):
    """Copy the crawled database into the data repo, push it, and post it."""
    logger.info(f"Publishing {database_path} to {data_repo_url}")

    # Resolve the branch rather than assuming one. sorrydb-data defaults to
    # master but sorrydb-data-test defaults to main and still has a stale
    # master, so a hardcoded name would publish where nobody reads.
    branch, _ = default_branch_head(data_repo_url)
    if branch is None:
        raise ValueError(f"Could not resolve the default branch of {data_repo_url}")
    logger.info(f"Publishing to the {branch} branch of {data_repo_url}")

    repo_path = prepare_repository(data_repo_url, branch, None, LOCAL_CLONE_PATH)

    shutil.copy2(database_path, repo_path / "sorry_database.json")
    for name in ("update_database_stats.json", "update_report.md"):
        source = database_path.parent / name
        if source.exists():
            shutil.copy2(source, repo_path / name)
        else:
            logger.info(f"No {name} to publish")

    deduplicated_file = repo_path / "deduplicated_sorries.json"
    deduplicate_database(
        database_path=repo_path / "sorry_database.json",
        query_results_path=deduplicated_file,
    )

    commit_and_push(repo_path, data_repo_url, token, branch, dry_run)

    if api_url:
        post_sorries(deduplicated_file, api_url, dry_run)
    else:
        logger.info("SORRYDB_API_URL is not set, skipping the leaderboard post")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("sorrydb").setLevel(logging.INFO)

    mode = os.environ.get("SORRYDB_MODE", "all")
    if mode not in MODES:
        raise ValueError(f"Unknown SORRYDB_MODE '{mode}'. Available: {', '.join(MODES)}")

    extractor_name = os.environ.get("SORRYDB_EXTRACTOR", "morph")
    if extractor_name not in EXTRACTORS:
        raise ValueError(
            f"Unknown SORRYDB_EXTRACTOR '{extractor_name}'. "
            f"Available: {', '.join(EXTRACTORS)}"
        )

    database_path = Path(
        os.environ.get("SORRYDB_DATABASE_PATH", DEFAULT_DATABASE_PATH)
    )
    data_repo_url = os.environ.get("SORRYDB_DATA_REPO_URL", DEFAULT_DATA_REPO_URL)
    api_url = os.environ.get("SORRYDB_API_URL")
    dry_run = bool(os.environ.get("SORRYDB_DRY_RUN"))
    all_branches = bool(os.environ.get("SORRYDB_ALL_BRANCHES"))

    token = os.environ.get("GITHUB_TOKEN")
    if mode in ("all", "publish") and not token and not dry_run:
        raise ValueError("GITHUB_TOKEN is required to push to the data repo")

    logger.info(f"Starting nightly update in {mode} mode (dry_run={dry_run})")

    if mode in ("all", "crawl"):
        crawl(database_path, extractor_name, all_branches)

    if mode in ("all", "publish"):
        publish(database_path, data_repo_url, token, api_url, dry_run)

    logger.info("Nightly update finished.")


if __name__ == "__main__":
    sys.exit(main())
