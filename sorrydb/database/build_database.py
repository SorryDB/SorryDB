import contextlib
import datetime
import json
import logging
import tempfile
from pathlib import Path
from typing import Callable, Optional

import requests

from sorrydb.database.process_sorries import prepare_and_process_lean_repo
from sorrydb.database.sorry import DebugInfo, Location, Metadata, RepoInfo, Sorry
from sorrydb.database.sorry_database import JsonDatabase
from sorrydb.utils.git_ops import leaf_commits, parse_remote, remote_heads_hash
from sorrydb.utils.lean_repo import LakeTimeoutError
from sorrydb.utils.lean_version import parse_toolchain_version, select_repl_tag
from sorrydb.utils.repl_ops import repl_tags

# Create a module-level logger
logger = logging.getLogger(__name__)

# An extractor builds a repository at a commit and returns
# {"metadata": {..., "lean_version": str}, "sorries": [...]}.
Extractor = Callable[[str, str, str, Path], dict]

# A commit lister returns (new remote heads hash, new leaf commits, listing time)
# for one repo. The hash is None when the repo has nothing new. The listing time
# becomes the repo's last_time_visited, so it is taken before the listing itself,
# otherwise a commit landing during the listing would be marked visited but never
# processed.
CommitLister = Callable[[dict], tuple[Optional[str], list, str]]


TOOLCHAIN_URL = "https://raw.githubusercontent.com/{owner}/{repo}/HEAD/lean-toolchain"
TOOLCHAIN_TIMEOUT = 30


def default_branch_toolchain(repo_url: str) -> str | None:
    """Fetch a repo's lean-toolchain at its default branch head, without cloning.

    Returns None when the repo positively has no lean-toolchain there. Raises for
    anything we could not determine, such as a non-GitHub remote or a network
    failure, so that callers can fail open rather than skip a repo by accident.
    """
    host, owner, repo = parse_remote(repo_url)
    if host != "github.com" or not owner or not repo:
        raise ValueError(f"Cannot fetch lean-toolchain for non-GitHub remote {repo_url}")

    response = requests.get(
        TOOLCHAIN_URL.format(owner=owner, repo=repo), timeout=TOOLCHAIN_TIMEOUT
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.text


def unsupported_toolchain_reason(toolchain: str | None, tags) -> Optional[str]:
    """Why the extractor cannot handle this toolchain, or None if it can."""
    if toolchain is None:
        return "no lean-toolchain at the default branch head"

    version = parse_toolchain_version(toolchain)
    if version is None:
        return f"unreadable lean-toolchain: {toolchain.strip()!r}"

    if select_repl_tag(version, tags) is None:
        return f"no REPL tag for Lean {version}"

    return None


def unsupported_toolchain_repos(
    repo_urls, resolve=default_branch_toolchain, tags=None
) -> dict:
    """Find the repos the extractor cannot handle, as {repo_url: reason}.

    Called in the listing pass so an unsupported repo never costs a build. The
    result is not stored anywhere, so a repo that upgrades its toolchain starts
    working again on its own, and re-checking is one HTTP request per repo.

    Fails open: a repo we could not resolve is not reported as unsupported, so
    the worst case is the build we would have run anyway.
    """
    if tags is None:
        tags = repl_tags()

    reasons = {}
    for repo_url in repo_urls:
        try:
            toolchain = resolve(repo_url)
        except Exception as e:
            logger.warning(f"Could not resolve toolchain for {repo_url}: {e}")
            continue

        reason = unsupported_toolchain_reason(toolchain, tags)
        if reason:
            reasons[repo_url] = reason

    return reasons


def local_extractor(
    repo_url: str, branch: str, commit_sha: str, lean_data: Path
) -> dict:
    """Extract sorries by building the repository on this machine."""
    return prepare_and_process_lean_repo(
        repo_url=repo_url, lean_data=lean_data, branch=branch, commit_sha=commit_sha
    )


def local_lister(repo: dict, all_branches: bool = False) -> tuple[Optional[str], list, str]:
    """List a repo's new leaf commits by querying its remote.

    Args:
        repo: repo entry from the database
        all_branches: crawl every branch head instead of only the default branch.
            Work scales with branch heads, since each one gets its own Lean
            build, and branches of one repo largely share goals, so the default
            is the default branch only. Pass
            functools.partial(local_lister, all_branches=True) as the
            CommitLister to opt back in.
    """
    listed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    new_remote_hash = repo_has_updates(repo, all_branches)
    if new_remote_hash is None:
        return None, [], listed_at
    return new_remote_hash, get_new_leaf_commits(repo, all_branches), listed_at


def cached_extractor(cache: dict) -> Extractor:
    """Replay extractions prefetched into `cache`, keyed by (repo_url, commit_sha).

    A missing entry, or an entry holding the exception that failed it, raises.
    process_new_commits logs that and moves on to the next commit, exactly as it
    does for a build that fails inline.
    """

    def extract(repo_url: str, branch: str, commit_sha: str, lean_data: Path) -> dict:
        result = cache[(repo_url, commit_sha)]
        if isinstance(result, BaseException):
            raise result
        return result

    return extract


def listings_to_work(listings: dict) -> list[tuple[str, str, str]]:
    """Flatten listings into the (repo_url, branch, commit_sha) list to extract.

    Branches sharing a head commit are extracted once rather than once per
    branch, since each extraction costs a whole VM.
    """
    work = []
    seen = set()
    for remote_url, (new_remote_hash, commits, _) in listings.items():
        if new_remote_hash is None:
            continue
        for commit in commits:
            key = (remote_url, commit["sha"])
            if key in seen:
                continue
            seen.add(key)
            work.append((remote_url, commit["branch"], commit["sha"]))
    return work


def cached_lister(listings: dict) -> CommitLister:
    """Replay listings made in an earlier pass, keyed by repo url.

    A repo with no listing is reported as having nothing new, so its watermarks
    stay put and it is picked up on the next run.
    """

    def list_commits(repo: dict) -> tuple[Optional[str], list, str]:
        listing = listings.get(repo["remote_url"])
        if listing is None:
            logger.warning(f"No prefetched listing for {repo['remote_url']}, skipping")
            return None, [], ""
        return listing

    return list_commits


def init_database(
    repo_list: list, starting_date: datetime.datetime, database_file: Path
):
    """
    Initialize a sorry database from a list of repositories.

    Args:
        repo_list: List of repository URLs to include in the database
        starting_date: Datetime object to use as the last_time_visited for all repos
        output_path: Path to save the database JSON file
    """
    logger.info(f"Initializing database from {len(repo_list)} repositories")
    # Create the initial database structure
    database = {"repos": [], "sorries": []}

    # Format the datetime as ISO 8601 string for JSON storage
    formatted_date = starting_date.isoformat()

    # Add each repository to the database
    for repo_url in repo_list:
        repo_entry = {
            "remote_url": repo_url,
            "last_time_visited": formatted_date,
            "remote_heads_hash": None,
        }
        database["repos"].append(repo_entry)

    # Write the database to the output file
    database_file.parent.mkdir(parents=True, exist_ok=True)
    with open(database_file, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2, ensure_ascii=False)

    logger.info(
        f"Initialized database with {len(repo_list)} repositories at {database_file}"
    )


def compute_new_sorries_stats(sorries) -> dict:
    """
    Compute statistics about a list of sorries.

    Args:
        sorries: List of sorry dictionaries

    Returns:
        dict: Statistics about the sorries, including count
    """
    if not sorries:
        return {"count": 0}

    return {"count": len(sorries)}


def process_new_commits(
    commits,
    remote_url,
    lean_data,
    database: JsonDatabase,
    extract: Extractor = local_extractor,
):
    """
    Process a list of new commits for a repository, building a Sorry object for each new sorry in the repo

    Args:

        commits: List of commit dictionaries to process
        remote_url: URL of the repository
        lean_data: Path to the lean data directory
        extract: Extractor used to build a commit and return its sorries
    Returns:
        int: how many commits extracted successfully
    """

    extracted = 0

    for commit in commits:
        logger.debug(f"processing commit on {remote_url}: {commit}")
        try:
            time_visited = datetime.datetime.now(datetime.timezone.utc)

            repo_results = extract(
                remote_url, commit["branch"], commit["sha"], lean_data
            )

            for sorry in repo_results["sorries"]:
                # Create dataclass instances for each component of the Sorry
                repo_info = RepoInfo(
                    remote=remote_url,
                    branch=commit["branch"],
                    commit=commit["sha"],
                    lean_version=repo_results["metadata"].get("lean_version", ""),
                )

                location = Location(
                    path=sorry["location"]["path"],
                    start_line=sorry["location"]["start_line"],
                    start_column=sorry["location"]["start_column"],
                    end_line=sorry["location"]["end_line"],
                    end_column=sorry["location"]["end_column"],
                )

                debug_info = DebugInfo(
                    goal=sorry["goal"],
                    url=f"{remote_url}/blob/{repo_info.commit}/{location.path}#L{location.start_line}",
                )

                blame_date = sorry["blame"]["date"]
                if isinstance(blame_date, str):
                    blame_date = datetime.datetime.fromisoformat(blame_date)

                metadata = Metadata(
                    blame_email_hash=sorry["blame"]["author_email_hash"],
                    blame_date=blame_date,
                    inclusion_date=time_visited,
                )

                # Sorry instance `id` field will be auto-generated
                sorry_instance = Sorry(
                    repo=repo_info,
                    location=location,
                    debug_info=debug_info,
                    metadata=metadata,
                )

                database.add_sorry(sorry_instance)

            try:
                commit_sorry_count = database.update_stats[remote_url][commit["sha"]][
                    "count"
                ]
            except (KeyError, TypeError):
                commit_sorry_count = 0

            logger.info(
                f"Processed commit {commit['sha']} with {commit_sorry_count} sorries"
            )
            extracted += 1

        except LakeTimeoutError:
            database.set_lake_timeout(remote_url, True)
            logger.warning(f"Lake timeout on {remote_url}. Skipping further processing")
            break  # if there is a Lake timeout skip processing the rest of the commits for this repo
        except Exception as e:
            logger.error(
                f"Error processing commit {commit} on repository {remote_url}: {e}"
            )
            logger.exception(e)
            continue  # Continue with next commit

    return extracted


def repo_has_updates(repo: dict, all_branches: bool = False) -> Optional[str]:
    """
    Check if a repository has updates by comparing remote heads hash.

    The hash must cover the same branches the crawl will read, otherwise a push
    to a branch we ignore triggers a listing pass that finds nothing to do.

    Returns:
        Optional[str]: The new remote heads hash if updates are available, None otherwise
    """
    remote_url = repo["remote_url"]
    logger.info(f"Checking repository for new commits: {remote_url}")

    try:
        current_hash = remote_heads_hash(remote_url, all_branches)
    except Exception:
        logger.exception(f"Could not get remote heads hash for {remote_url}, skipping.")
        return None

    if current_hash == repo["remote_heads_hash"]:
        logger.info(f"No changes detected for {remote_url}, skipping")
        return None

    logger.info(f"New commits detected for {remote_url}, processing...")
    return current_hash


def get_new_leaf_commits(repo: dict, all_branches: bool = False) -> list:
    remote_url = repo["remote_url"]

    all_commits = leaf_commits(remote_url, all_branches)

    last_visited = datetime.datetime.fromisoformat(repo["last_time_visited"])
    new_leaf_commits = []

    for commit in all_commits:
        commit_date = datetime.datetime.fromisoformat(commit["date"])

        if commit_date > last_visited:
            new_leaf_commits.append(commit)
            logger.info(
                f"Including new commit {commit['sha']} on branch {commit['branch']} from {commit_date.isoformat()}"
            )
        else:
            logger.debug(
                f"Skipping old commit {commit['sha']} on branch {commit['branch']} from {commit_date.isoformat()}"
            )

    logger.info(
        f"Filtered {len(all_commits)} commits to {len(new_leaf_commits)} new commits after {last_visited.isoformat()}"
    )
    return new_leaf_commits


def find_new_sorries(
    repo,
    lean_data_path,
    database: JsonDatabase,
    extract: Extractor = local_extractor,
    list_commits: CommitLister = local_lister,
    unsupported_toolchains: Optional[dict] = None,
):
    """
    Find new sorries in a repository since the last time it was visited.

    Returns:
        tuple: (list of new sorries, dict of statistics by commit)
    """
    reason = (unsupported_toolchains or {}).get(repo["remote_url"])
    if reason:
        # Not a failure, just nothing we can do with this repo yet. Returning
        # before touching the watermarks keeps the re-check cheap and lets the
        # repo start working by itself once it upgrades its toolchain.
        logger.info(f"Skipping {repo['remote_url']}: {reason}")
        database.set_unsupported_toolchain(repo["remote_url"], reason)
        return

    # only look for new sorries if the repo has updates since the last update
    new_remote_hash, new_leaf_commits, time_before_processing_repo = list_commits(repo)
    if new_remote_hash is None:
        logger.info(f"No new leaf commits for {repo['remote_url']}")
        database.set_new_leaf_commit(repo["remote_url"], False)
        return
    else:
        database.set_new_leaf_commit(repo["remote_url"], True)

    database.set_start_processing_time(repo["remote_url"], time_before_processing_repo)

    with (
        # if user provides a lean_data_path,
        # use a nullcontext to wrap the path
        contextlib.nullcontext(lean_data_path)
        if lean_data_path
        # otherwise use a temporary directory
        else tempfile.TemporaryDirectory()
    ) as lean_data_dir:
        lean_data_path = Path(lean_data_dir)
        logger.info(f"Using directory for lean data: {lean_data_dir}")
        extracted = process_new_commits(
            new_leaf_commits, repo["remote_url"], lean_data_path, database, extract
        )

    if new_leaf_commits and not extracted:
        # Nothing extracted at all, so advancing the watermarks would lose these
        # commits for good. Leave them and retry the repo on the next run. This
        # also covers the lake timeout, which breaks out on the first commit.
        # Partial failures still advance: re-extracting the commits that did
        # succeed costs a VM each and add_sorry does not deduplicate.
        logger.warning(
            f"No commit of {repo['remote_url']} extracted, leaving it to be retried"
        )
    else:
        # update repo with new time visited and remote hash
        repo["last_time_visited"] = time_before_processing_repo
        repo["remote_heads_hash"] = new_remote_hash

    # record the time after finishing processing the repo
    time_after_processing_repo = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()
    database.set_end_processing_time(repo["remote_url"], time_after_processing_repo)


def update_database(
    database_path: Path,
    write_database_path: Optional[Path] = None,
    lean_data_path: Optional[Path] = None,
    stats_file: Optional[Path] = None,
    report_file: Optional[Path] = None,
    extract: Extractor = local_extractor,
    list_commits: CommitLister = local_lister,
    unsupported_toolchains: Optional[dict] = None,
) -> dict:
    """
    Update a SorryDatabase by checking for changes in repositories and processing new commits.

    Args:
        database_path: Path to the database JSON file
        write_database_path: Path to write the databse JSON file (default: database_path)
        lean_data: Path to the lean data directory (default: create temporary directory)
        stats_file: file to write database stats (default: don't write statistics to file)
        extract: Extractor used to build a commit and return its sorries
        list_commits: CommitLister used to find each repo's new leaf commits
        unsupported_toolchains: {repo_url: reason} of repos to skip without
            advancing their watermarks, from unsupported_toolchain_repos
    Returns:
        update_database_stats: statistics on the sorries that were added to the database
    """

    if not write_database_path:
        write_database_path = database_path

    database = JsonDatabase()

    database.load_database(database_path)

    for repo in database.get_all_repos():
        find_new_sorries(
            repo,
            lean_data_path,
            database,
            extract,
            list_commits,
            unsupported_toolchains,
        )
        # Checkpoint after every repo so an interrupted run can resume
        # from the per-repo watermarks instead of starting over.
        database.write_database(write_database_path)

    database.write_database(write_database_path)
    if stats_file:
        database.write_stats(stats_file)

    if report_file:
        database.write_stats_report(report_file)

    return database.update_stats
