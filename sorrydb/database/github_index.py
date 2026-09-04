"""Index Lean repositories directly from the GitHub API.

TEMPORARY. Reservoir's index is missing repositories that meet its own
inclusion criteria: its discovery query (`filename:lake-manifest.json path:/`)
now matches more repositories than GitHub's 1000-result code search cap, and
the overflow is silently dropped. See
https://github.com/leanprover/reservoir/issues/109.

This module reimplements that discovery, sharding the code search by file size
so no single shard hits the cap, and applies Reservoir's inclusion criteria: a
root `lake-manifest.json` and an OSI-approved license.

Stars and recency are deliberately not applied. They are activity policy, and
the crawl recomputes eligibility from them on every run, so this module emits
the whole universe with each repo's stars, last activity and node id as data.
`fetch_repo_metadata` refreshes those nightly for a database that already
exists.

Delete this module and go back to the Reservoir index once the upstream issue is
fixed.
"""

import json
import logging
import math
import os
import time
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
MANIFEST_QUERY = "filename:lake-manifest.json path:/"
# GitHub never returns more than 1000 results for a single search query.
SEARCH_RESULT_CAP = 1000
# No lake-manifest.json is anywhere near this large.
MAX_MANIFEST_SIZE = 2**20
SPDX_LICENSE_URL = (
    "https://raw.githubusercontent.com/spdx/license-list-data/main/json/licenses.json"
)

REPO_QUERY = """
query($repoIds: [ID!]!) {
  nodes(ids: $repoIds) {
    ... on Repository {
      id
      nameWithOwner
      url
      licenseInfo { spdxId }
      updatedAt
      pushedAt
      stargazerCount
    }
  }
}
"""


def _session():
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "SorryDB",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not token:
        raise RuntimeError(
            "GitHub code search requires authentication; set GITHUB_TOKEN or GH_TOKEN"
        )
    session.headers["Authorization"] = f"Bearer {token}"
    return session


def _request(session, method, endpoint, **kwargs):
    """Call the GitHub API, waiting out rate limits.

    Code search allows only 10 requests/minute, so being throttled is expected
    rather than exceptional.
    """
    while True:
        resp = session.request(method, f"{GITHUB_API}/{endpoint}", timeout=30, **kwargs)
        if resp.status_code in (403, 429):
            retry_after = resp.headers.get("retry-after")
            reset = resp.headers.get("x-ratelimit-reset")
            if retry_after:
                delay = int(retry_after)
            elif resp.headers.get("x-ratelimit-remaining") == "0" and reset:
                delay = max(0, int(reset) - int(time.time()))
            else:
                resp.raise_for_status()
            logger.info(f"Rate limited by GitHub, waiting {delay + 1}s")
            time.sleep(delay + 1)
            continue
        resp.raise_for_status()
        return resp.json()


def _search_page(session, lo, hi, page):
    return _request(
        session,
        "GET",
        "search/code",
        params={
            "q": f"{MANIFEST_QUERY} size:{lo}..{hi}",
            "per_page": 100,
            "page": page,
        },
    )


def size_shards(count_in_range, lo=0, hi=MAX_MANIFEST_SIZE, cap=SEARCH_RESULT_CAP):
    """Split the manifest size range into shards that each fit under `cap`.

    `count_in_range(lo, hi)` returns how many results GitHub reports for that
    inclusive byte range. Splits geometrically rather than at the arithmetic
    midpoint, because manifest sizes cluster at the small end.
    """
    shards = []
    todo = [(lo, hi)]
    while todo:
        lo, hi = todo.pop()
        count = count_in_range(lo, hi)
        if count == 0:
            continue
        if count <= cap or lo >= hi:
            if count > cap:
                logger.warning(
                    f"{count} manifests all of size {lo}B exceed the "
                    f"{cap}-result cap; some repositories will be missed"
                )
            shards.append((lo, hi))
            continue
        mid = int(math.sqrt(max(lo, 1) * hi))
        mid = min(max(mid, lo), hi - 1)
        todo.append((mid + 1, hi))
        todo.append((lo, mid))
    return shards


def search_repo_ids(session):
    """Return the node IDs of all repositories with a root lake-manifest.json."""
    counts = {}

    def count_in_range(lo, hi):
        if (lo, hi) not in counts:
            counts[(lo, hi)] = _search_page(session, lo, hi, 1)["total_count"]
        return counts[(lo, hi)]

    repo_ids = set()
    for lo, hi in size_shards(count_in_range):
        page = 1
        while True:
            results = _search_page(session, lo, hi, page)
            repo_ids.update(item["repository"]["node_id"] for item in results["items"])
            # Search results are capped at 1000 (10 pages of 100).
            if len(results["items"]) < 100 or page == 10:
                break
            page += 1
        logger.info(f"size {lo}..{hi}: {results['total_count']} manifests")
    logger.info(f"{len(repo_ids)} candidate repositories with root Lake manifests")
    return sorted(repo_ids)


def fetch_repos(session, repo_ids):
    """Fetch repository metadata for `repo_ids` via the GraphQL API.

    `nodes(ids:)` is partial by design: an id that no longer resolves, because
    the repo was deleted or went private, comes back as null in its slot plus a
    NOT_FOUND entry in `errors`, while the rest of the batch resolves fine. Keep
    what resolved. One deleted repo used to fail the whole nightly metadata
    refresh, which then fell back to metadata frozen at the last good run.

    Any other error still raises: a bad token, a rate limit or a malformed query
    must not be reported as a handful of repos that happen to be missing, since
    refresh_repo_metadata retires the repos that do not come back.
    """
    repos = []
    for i in range(0, len(repo_ids), 100):
        batch = repo_ids[i : i + 100]
        result = _request(
            session,
            "POST",
            "graphql",
            json={"query": REPO_QUERY, "variables": {"repoIds": batch}},
        )
        errors = result.get("errors", [])
        fatal = [error for error in errors if error.get("type") != "NOT_FOUND"]
        if fatal:
            raise RuntimeError(f"GitHub GraphQL query failed: {fatal}")
        if errors:
            logger.warning(f"{len(errors)} repo ids no longer resolve on GitHub")
        repos.extend(repo for repo in result["data"]["nodes"] if repo)
    return repos


def osi_license_ids():
    """SPDX IDs of OSI-approved licenses, the license criterion Reservoir uses."""
    resp = requests.get(SPDX_LICENSE_URL, timeout=30)
    resp.raise_for_status()
    return {
        license["licenseId"]
        for license in resp.json()["licenses"]
        if license.get("isOsiApproved", False)
    }


def repo_entry(repo):
    """One index entry, in the shape build_database.repo_record consumes."""
    license_info = repo["licenseInfo"]
    return {
        "remote": repo["url"],
        # Stable across renames, and what fetch_repos queries by, so a nightly
        # metadata refresh needs no URL to node id lookup.
        "node_id": repo["id"],
        "stars": repo["stargazerCount"],
        # Reservoir treats a package as updated at the later of the two.
        "last_activity": max(repo["updatedAt"], repo["pushedAt"]),
        "license": license_info["spdxId"] if license_info else None,
    }


def apply_inclusion_criteria(repos, osi_licenses):
    """Keep the repos meeting the inclusion criteria, with their metadata.

    Inclusion criteria only: a root lake-manifest.json, already applied by the
    code search, and an OSI-approved license. Stars and recency are deliberately
    not applied. They are activity policy, they change, and the crawl recomputes
    eligibility from them every run, so baking a star floor into this artifact
    would silently and permanently shrink the universe.
    """
    entries = []
    for repo in repos:
        license_info = repo["licenseInfo"]
        if not license_info or license_info["spdxId"] not in osi_licenses:
            continue
        entries.append(repo_entry(repo))
    return entries


def fetch_repo_metadata(repos):
    """Refresh stars and last activity for database repo records.

    The fetch_metadata seam of build_database.refresh_eligibility: takes the
    stored records and returns {remote_url: {stars, last_activity, license}}.

    Queries by the stored node id, which costs no extra calls and is stable
    across renames, then maps back to the URL the database already holds, so a
    renamed repo still refreshes instead of quietly going stale. A record with
    no node id, from an index generated before they were stored, is skipped and
    keeps its stored metadata until the index is regenerated.
    """
    url_by_node_id = {
        repo["node_id"]: repo["remote_url"] for repo in repos if repo.get("node_id")
    }
    if not url_by_node_id:
        logger.warning("No repo node ids stored, cannot refresh metadata")
        return {}

    fetched = fetch_repos(_session(), sorted(url_by_node_id))
    return {
        url_by_node_id[repo["id"]]: {
            "stars": repo["stargazerCount"],
            "last_activity": max(repo["updatedAt"], repo["pushedAt"]),
            "license": repo["licenseInfo"]["spdxId"] if repo["licenseInfo"] else None,
        }
        for repo in fetched
        if repo["id"] in url_by_node_id
    }


def index_github(output):
    """Write the whole universe of repos meeting the inclusion criteria."""
    session = _session()
    candidates = fetch_repos(session, search_repo_ids(session))
    entries = apply_inclusion_criteria(candidates, osi_license_ids())
    logger.info(
        f"{len(entries)} of {len(candidates)} candidates meet the inclusion criteria"
    )

    output_data = {
        "documentation": (
            "The universe of Lean repositories meeting the inclusion criteria, "
            f"pulled from the GitHub API. Generated on {datetime.now().isoformat()}. "
            "Includes every public repository with a root lake-manifest.json and an "
            "OSI-approved license, with its stars and last activity as data rather "
            "than as filters: the crawl recomputes eligibility from those each run, "
            "so this is not a pre-filtered active list. Replaces the reservoir index "
            "while https://github.com/leanprover/reservoir/issues/109 is open."
        ),
        "repos": entries,
    }
    with open(output, "w") as f:
        json.dump(output_data, f, indent=2)
