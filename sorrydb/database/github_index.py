"""Index Lean repositories directly from the GitHub API.

TEMPORARY. Reservoir's index is missing repositories that meet its own
inclusion criteria: its discovery query (`filename:lake-manifest.json path:/`)
now matches more repositories than GitHub's 1000-result code search cap, and
the overflow is silently dropped. See
https://github.com/leanprover/reservoir/issues/109.

This module reimplements that discovery, sharding the code search by file size
so no single shard hits the cap, and applies the same inclusion criteria
Reservoir does (root `lake-manifest.json`, OSI-approved license, minimum
stars). Output format is identical to `sorrydb.database.reservoir`.

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
    """Fetch repository metadata for `repo_ids` via the GraphQL API."""
    repos = []
    for i in range(0, len(repo_ids), 100):
        batch = repo_ids[i : i + 100]
        result = _request(
            session,
            "POST",
            "graphql",
            json={"query": REPO_QUERY, "variables": {"repoIds": batch}},
        )
        if "errors" in result:
            raise RuntimeError(f"GitHub GraphQL query failed: {result['errors']}")
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


def filter_repos(repos, updated_since, minimum_stars, osi_licenses):
    """Apply Reservoir's inclusion criteria plus SorryDB's activity criteria."""
    remotes = []
    for repo in repos:
        if repo["stargazerCount"] < minimum_stars:
            continue
        license_info = repo["licenseInfo"]
        if not license_info or license_info["spdxId"] not in osi_licenses:
            continue
        # Reservoir treats a package as updated at the later of the two.
        updated_at = max(repo["updatedAt"], repo["pushedAt"])
        if datetime.fromisoformat(updated_at.replace("Z", "+00:00")) < updated_since:
            continue
        remotes.append({"remote": repo["url"]})
    return remotes


def index_github(updated_since, minimum_stars, output):
    session = _session()
    repos = fetch_repos(session, search_repo_ids(session))
    repos = filter_repos(repos, updated_since, minimum_stars, osi_license_ids())
    logger.info(f"{len(repos)} repositories meet all criteria")

    output_data = {
        "documentation": f"List of active repositories pulled from the GitHub API. Generated on {datetime.now().isoformat()}. Includes public repositories with a root lake-manifest.json and an OSI-approved license which have been updated since {updated_since} and have at least {minimum_stars} GitHub stars. Replaces the reservoir index while https://github.com/leanprover/reservoir/issues/109 is open.",
        "repos": repos,
    }
    with open(output, "w") as f:
        json.dump(output_data, f, indent=2)
