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
        token="token",
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
        token="token",
        branch="main",
        dry_run=True,
    )

    assert Repo(bare).heads == []
    assert "Updating SorryDB at" in Repo(work).heads.main.commit.message
