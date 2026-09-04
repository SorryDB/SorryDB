from sorrydb.database.github_index import size_shards


def counter(sizes):
    """Stand-in for GitHub's `total_count` over an inclusive size range."""
    return lambda lo, hi: sum(1 for size in sizes if lo <= size <= hi)


def check_covers(shards, sizes, cap):
    # every size lands in exactly one shard
    for size in sizes:
        assert sum(1 for lo, hi in shards if lo <= size <= hi) == 1
    for lo, hi in shards:
        assert counter(sizes)(lo, hi) <= cap or lo == hi


def test_shards_split_until_under_cap():
    # 2500 manifests clustered where real ones are, well over the cap
    sizes = [200 + (i * 7) % 4000 for i in range(2500)]
    shards = size_shards(counter(sizes), cap=1000)
    check_covers(shards, sizes, 1000)


def test_no_split_needed():
    sizes = [500, 1500, 90000]
    assert size_shards(counter(sizes), cap=1000) == [(0, 1024 * 1024)]


def test_unsplittable_shard_still_covers():
    # 2000 manifests of identical size cannot be split below the cap
    sizes = [500] * 2000
    shards = size_shards(counter(sizes), cap=1000)
    check_covers(shards, sizes, 1000)
    assert any(lo == hi == 500 for lo, hi in shards)


# --- metadata refresh --------------------------------------------------------


def test_apply_inclusion_criteria_keeps_metadata_and_drops_unlicensed():
    from sorrydb.database.github_index import apply_inclusion_criteria

    candidates = [
        {
            "id": "N1",
            "url": "https://github.com/o/licensed",
            "nameWithOwner": "o/licensed",
            "licenseInfo": {"spdxId": "Apache-2.0"},
            "updatedAt": "2026-01-01T00:00:00Z",
            "pushedAt": "2026-06-01T00:00:00Z",
            "stargazerCount": 3,
        },
        {
            "id": "N2",
            "url": "https://github.com/o/unlicensed",
            "nameWithOwner": "o/unlicensed",
            "licenseInfo": None,
            "updatedAt": "2026-01-01T00:00:00Z",
            "pushedAt": "2026-01-01T00:00:00Z",
            "stargazerCount": 5000,
        },
        {
            "id": "N3",
            "url": "https://github.com/o/proprietary",
            "nameWithOwner": "o/proprietary",
            "licenseInfo": {"spdxId": "LicenseRef-Custom"},
            "updatedAt": "2026-01-01T00:00:00Z",
            "pushedAt": "2026-01-01T00:00:00Z",
            "stargazerCount": 5000,
        },
    ]

    entries = apply_inclusion_criteria(candidates, {"Apache-2.0", "MIT"})

    # only the license criterion applies: 3 stars and a stale date are kept
    assert entries == [
        {
            "remote": "https://github.com/o/licensed",
            "node_id": "N1",
            "stars": 3,
            "last_activity": "2026-06-01T00:00:00Z",  # the later of the two
            "license": "Apache-2.0",
        }
    ]


def test_fetch_repo_metadata_maps_node_ids_back_to_stored_urls(monkeypatch):
    """Querying by node id costs no lookup and survives a rename."""
    from sorrydb.database import github_index

    monkeypatch.setattr(github_index, "_session", lambda: "session")

    def fake_fetch_repos(session, node_ids):
        assert session == "session"
        assert node_ids == ["N1", "N2"]
        return [
            {
                "id": "N1",
                "url": "https://github.com/o/one",
                "licenseInfo": {"spdxId": "MIT"},
                "updatedAt": "2026-08-01T00:00:00Z",
                "pushedAt": "2026-09-01T00:00:00Z",
                "stargazerCount": 42,
            },
            {
                # renamed since indexing: GitHub reports the new URL
                "id": "N2",
                "url": "https://github.com/o/renamed",
                "licenseInfo": None,
                "updatedAt": "2026-07-01T00:00:00Z",
                "pushedAt": "2026-07-01T00:00:00Z",
                "stargazerCount": 7,
            },
        ]

    monkeypatch.setattr(github_index, "fetch_repos", fake_fetch_repos)

    repos = [
        {"remote_url": "https://github.com/o/one", "node_id": "N1"},
        {"remote_url": "https://github.com/o/old-name", "node_id": "N2"},
        {"remote_url": "https://github.com/o/no-id"},  # pre node id record
    ]

    metadata = github_index.fetch_repo_metadata(repos)

    # keyed by the URL the database holds, so the renamed repo still refreshes
    assert metadata == {
        "https://github.com/o/one": {
            "stars": 42,
            "last_activity": "2026-09-01T00:00:00Z",
            "license": "MIT",
        },
        "https://github.com/o/old-name": {
            "stars": 7,
            "last_activity": "2026-07-01T00:00:00Z",
            "license": None,
        },
    }
    # the record with no node id is simply absent, so it keeps stored metadata
    assert "https://github.com/o/no-id" not in metadata


def test_fetch_repo_metadata_without_node_ids_refreshes_nothing():
    from sorrydb.database.github_index import fetch_repo_metadata

    assert fetch_repo_metadata([{"remote_url": "https://github.com/o/r"}]) == {}


def test_fetch_repos_keeps_the_nodes_that_resolved(monkeypatch):
    """A deleted repo must not fail the refresh for every other repo.

    On 2026-09-03 one 3-star repo indexed two days earlier had been deleted, so
    its node id yielded a NOT_FOUND and the whole nightly metadata refresh
    failed. Every eligibility verdict in that run came from stored metadata.
    """
    from sorrydb.database import github_index

    def fake_request(session, method, path, json):
        return {
            "data": {"nodes": [{"id": "N1"}, None, {"id": "N3"}]},
            "errors": [
                {
                    "type": "NOT_FOUND",
                    "path": ["nodes", 1],
                    "message": "Could not resolve to a node with the global id of 'N2'",
                }
            ],
        }

    monkeypatch.setattr(github_index, "_request", fake_request)

    assert github_index.fetch_repos("session", ["N1", "N2", "N3"]) == [
        {"id": "N1"},
        {"id": "N3"},
    ]


def test_fetch_repos_still_raises_on_a_real_error(monkeypatch):
    """A bad token or a rate limit must stay a hard failure.

    refresh_repo_metadata retires the repos that do not come back, so reporting
    a broken query as "these repos are missing" would retire the whole index.
    """
    import pytest

    from sorrydb.database import github_index

    def fake_request(session, method, path, json):
        return {
            "data": None,
            "errors": [{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}],
        }

    monkeypatch.setattr(github_index, "_request", fake_request)

    with pytest.raises(RuntimeError, match="RATE_LIMITED"):
        github_index.fetch_repos("session", ["N1"])
