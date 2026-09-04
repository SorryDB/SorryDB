"""Tests for the publish path.

The data repos disagree about their default branch: sorrydb-data uses master,
sorrydb-data-test uses main and still has a stale master that nobody reads.
Publishing to a hardcoded branch name therefore looks like success while
writing where nobody looks, so the branch must come from the remote.
"""

import json

from git import Repo

from orchestration import nightly_update


def test_publish_uses_the_branch_the_remote_calls_default(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()

    database_path = tmp_path / "sorry_database.json"
    database_path.write_text(json.dumps({"repos": [], "sorries": []}))

    prepared = {}
    pushed = {}

    def fake_default_branch_head(remote_url):
        return "main", "f3f7aed4"

    def fake_prepare_repository(remote_url, branch, head_sha, lean_data):
        prepared["remote_url"] = remote_url
        prepared["branch"] = branch
        prepared["head_sha"] = head_sha
        return checkout

    def fake_commit_and_push(repo_path, data_repo_url, token, branch, dry_run):
        pushed["branch"] = branch
        pushed["dry_run"] = dry_run

    monkeypatch.setattr(nightly_update, "default_branch_head", fake_default_branch_head)
    monkeypatch.setattr(nightly_update, "prepare_repository", fake_prepare_repository)
    monkeypatch.setattr(nightly_update, "commit_and_push", fake_commit_and_push)

    nightly_update.publish(
        database_path=database_path,
        data_repo_url="https://github.com/SorryDB/sorrydb-data-test.git",
        token="token",
        api_url=None,  # skips the leaderboard post
        dry_run=False,
    )

    # the resolved branch is what gets checked out and what gets pushed
    assert prepared["branch"] == "main"
    assert pushed["branch"] == "main"
    assert "master" not in (prepared["branch"], pushed["branch"])

    # the database still reaches the checkout, under the name the data repo uses
    assert (checkout / "sorry_database.json").exists()
    assert (checkout / "deduplicated_sorries.json").exists()


def test_publish_refuses_to_guess_a_branch(tmp_path, monkeypatch):
    """Better to fail than to fall back to a name that may be the stale one."""
    import pytest

    database_path = tmp_path / "sorry_database.json"
    database_path.write_text(json.dumps({"repos": [], "sorries": []}))

    monkeypatch.setattr(
        nightly_update, "default_branch_head", lambda remote_url: (None, None)
    )

    with pytest.raises(ValueError, match="default branch"):
        nightly_update.publish(
            database_path=database_path,
            data_repo_url="https://github.com/SorryDB/sorrydb-data-test.git",
            token="token",
            api_url=None,
            dry_run=False,
        )


def test_commit_and_push_pushes_the_resolved_branch_and_tag(tmp_path):
    """Real git, local remote, no network: the commit must land on main."""
    bare = tmp_path / "remote.git"
    Repo.init(bare, bare=True, initial_branch="main")

    work = tmp_path / "work"
    work.mkdir()
    checkout = Repo.init(work, initial_branch="main")
    checkout.create_remote("origin", str(bare))
    (work / "sorry_database.json").write_text("{}")

    nightly_update.commit_and_push(
        repo_path=work,
        data_repo_url=str(bare),
        token=None,  # a local push needs no token
        branch="main",
        dry_run=False,
    )

    remote = Repo(bare)
    assert [h.name for h in remote.heads] == ["main"]
    assert "Updating SorryDB at" in remote.heads.main.commit.message
    assert len(remote.tags) == 1  # the daily tag


def test_commit_and_push_does_not_push_on_a_dry_run(tmp_path):
    bare = tmp_path / "remote.git"
    Repo.init(bare, bare=True, initial_branch="main")

    work = tmp_path / "work"
    work.mkdir()
    checkout = Repo.init(work, initial_branch="main")
    checkout.create_remote("origin", str(bare))
    (work / "sorry_database.json").write_text("{}")

    nightly_update.commit_and_push(
        repo_path=work,
        data_repo_url=str(bare),
        token=None,  # a local push needs no token
        branch="main",
        dry_run=True,
    )

    assert Repo(bare).heads == []
    assert "Updating SorryDB at" in Repo(work).heads.main.commit.message


def test_push_url_refuses_a_non_https_url_with_a_token():
    """Silently returning the URL unchanged surfaced as an opaque auth failure."""
    import pytest

    assert nightly_update._push_url("https://github.com/o/r.git", "tok") == (
        "https://x-access-token:tok@github.com/o/r.git"
    )
    # no token, nothing to attach, nothing to complain about
    assert nightly_update._push_url("git@github.com:o/r.git", None) == (
        "git@github.com:o/r.git"
    )
    with pytest.raises(ValueError, match="must be https"):
        nightly_update._push_url("git@github.com:o/r.git", "tok")


def test_crawl_only_spends_network_and_vms_on_crawlable_repos(tmp_path, monkeypatch):
    """The gate has to hold at the call site, not just in the helper.

    The first full run passed every repo to the listing pass, so it built 399
    repos that process_new_commits then discarded for having fewer than 10
    stars: 80% of its VMs, and about six of its seven hours.
    """
    database_path = tmp_path / "sorry_database.json"
    database_path.write_text(json.dumps({"sorries": [], "repos": [
        {"remote_url": "https://github.com/o/eligible", "eligible": True,
         "last_time_visited": "2026-08-25T00:00:00+00:00", "remote_heads_hash": None},
        {"remote_url": "https://github.com/o/too-few-stars", "eligible": False,
         "ineligible_reason": "fewer than 10 stars",
         "last_time_visited": "2026-08-25T00:00:00+00:00", "remote_heads_hash": None},
    ]}))

    toolchain_checked, prefetched = [], []

    monkeypatch.setattr(nightly_update, "unsupported_toolchain_repos",
                        lambda urls: toolchain_checked.extend(urls) or {})
    monkeypatch.setattr(nightly_update, "local_lister",
                        lambda repo: ("hash", [("main", "c0ffee")], "now"))
    monkeypatch.setattr(nightly_update, "listings_to_work",
                        lambda listings: [(url, "main", "c0ffee") for url in listings])
    monkeypatch.setattr(nightly_update, "update_database", lambda **kwargs: None)

    from sorrydb.runners import morphcloud_crawler
    monkeypatch.setattr(morphcloud_crawler, "sweep_orphaned_instances", lambda *a, **k: None)
    monkeypatch.setattr(morphcloud_crawler, "prefetch",
                        lambda work, max_workers=8: prefetched.extend(work) or {})

    nightly_update.crawl(database_path, "morph", all_branches=False)

    assert toolchain_checked == ["https://github.com/o/eligible"]
    assert [w[0] for w in prefetched] == ["https://github.com/o/eligible"]


def test_the_listing_pass_skips_repos_the_crawl_would_discard():
    """The listing pass must gate on the same verdict process_new_commits does.

    It did not, and the first full run listed and built 399 repos that
    process_new_commits then dropped for having fewer than 10 stars: 80% of its
    VMs. Only the toolchain was checked here.
    """
    repos = [
        {"remote_url": "https://github.com/o/eligible", "eligible": True},
        {"remote_url": "https://github.com/o/no-verdict-yet"},
        {"remote_url": "https://github.com/o/too-few-stars", "eligible": False},
        {"remote_url": "https://github.com/o/bad-toolchain", "eligible": True},
    ]
    crawlable = [r for r in repos if nightly_update.is_crawlable(r)]
    unsupported = {"https://github.com/o/bad-toolchain": "no REPL tag"}

    listed = nightly_update.list_new_commits(
        crawlable, lambda repo: ("hash", [], "now"), unsupported
    )

    assert set(listed) == {
        "https://github.com/o/eligible",
        # no verdict yet is crawlable, the defensive case
        "https://github.com/o/no-verdict-yet",
    }


def test_replace_sorries_sends_the_whole_set_in_one_request(tmp_path, monkeypatch):
    """The API replaces the set it is given, so it has to see all of it at once.

    Split across chunks the server could not tell a sorry that is gone from one
    that is in the chunk still to come, so it could not reconcile.
    """
    sorries_path = tmp_path / "sorry_database.json"
    sorries_path.write_text(
        json.dumps({"repos": [], "sorries": [{"id": str(i)} for i in range(1200)]})
    )

    posts = []

    class FakeResponse:
        def __init__(self, body):
            self.body = body

        def raise_for_status(self):
            pass

        def json(self):
            return self.body

    def fake_post(url, data, timeout):
        assert url == "https://api.sorrydb.org/auth/token"
        assert data == {"username": "nightly@sorrydb.org", "password": "secret"}
        return FakeResponse({"access_token": "a-token"})

    def fake_put(url, json, headers, timeout):
        posts.append((url, json, headers))
        return FakeResponse({"stored": len(json), "retired": 0})

    monkeypatch.setattr(nightly_update.requests, "post", fake_post)
    monkeypatch.setattr(nightly_update.requests, "put", fake_put)

    nightly_update.replace_sorries(
        sorries_path,
        "https://api.sorrydb.org/",
        "nightly@sorrydb.org",
        "secret",
        dry_run=False,
    )

    assert len(posts) == 1
    url, payload, headers = posts[0]
    assert url == "https://api.sorrydb.org/sorries/"
    assert len(payload) == 1200
    # the endpoint is admin only, because the body replaces the whole set
    assert headers["Authorization"] == "Bearer a-token"
