"""PUT /sorries/ replaces the stored set with the posted one.

Postgres is a derived read model of sorry_database.json, not a store of record,
so the nightly job posts the whole dataset and this endpoint reconciles: what is
in the body is stored, what is missing from it is retired. Retirement is a flag
rather than a delete because challenge.sorry_id points at these rows.
"""

import json
from pathlib import Path

from sqlmodel import col, func, select

from sorrydb.leaderboard.model.sorry import SQLSorry


def load_multiple_sorries_as_json() -> dict:
    project_root = Path(__file__).resolve().parent.parent.parent
    sample_sorries_path = project_root / "doc" / "sample_sorry_list.json"
    with open(sample_sorries_path, "r") as f:
        return json.load(f)["sorries"]


def load_single_sorry_as_json() -> dict:
    return load_multiple_sorries_as_json()[0]


def put_sorries(client, admin_auth_headers, sorries):
    return client.put("/sorries/", json=sorries, headers=admin_auth_headers)


def stored_ids(session, retired=False):
    condition = (
        col(SQLSorry.retired_at).is_not(None)
        if retired
        else col(SQLSorry.retired_at).is_(None)
    )
    return set(session.exec(select(SQLSorry.id).where(condition)).all())


def test_replace_stores_the_posted_set(client, admin_auth_headers):
    sorries = load_multiple_sorries_as_json()
    response = put_sorries(client, admin_auth_headers, sorries)
    assert response.status_code == 200
    assert response.json() == {"stored": len(sorries), "retired": 0}


def test_replacing_with_the_same_set_does_not_duplicate(
    client, session, admin_auth_headers
):
    """The nightly job re-posts the whole dataset every night."""
    sorries = load_multiple_sorries_as_json()

    for _ in range(2):
        assert put_sorries(client, admin_auth_headers, sorries).json() == {
            "stored": len(sorries),
            "retired": 0,
        }

    stored = session.exec(select(func.count()).select_from(SQLSorry)).one()
    assert stored == len(sorries)


def test_a_sorry_missing_from_the_next_post_is_retired_not_deleted(
    client, session, admin_auth_headers
):
    sorries = load_multiple_sorries_as_json()
    put_sorries(client, admin_auth_headers, sorries)
    everything = stored_ids(session)

    kept = sorries[:1]
    assert put_sorries(client, admin_auth_headers, kept).json() == {
        "stored": 1,
        "retired": len(sorries) - 1,
    }

    session.expire_all()
    assert len(stored_ids(session)) == 1
    # still there, so a challenge against one of them can still resolve
    assert stored_ids(session) | stored_ids(session, retired=True) == everything


def test_a_sorry_that_comes_back_stops_being_retired(
    client, session, admin_auth_headers
):
    """A repo reverts, or a half-failed run is re-run, and the sorry returns."""
    sorries = load_multiple_sorries_as_json()
    put_sorries(client, admin_auth_headers, sorries)
    put_sorries(client, admin_auth_headers, sorries[:1])

    session.expire_all()
    assert stored_ids(session, retired=True)

    assert put_sorries(client, admin_auth_headers, sorries).json() == {
        "stored": len(sorries),
        "retired": 0,
    }
    session.expire_all()
    assert stored_ids(session, retired=True) == set()


def test_the_list_endpoint_hides_retired_sorries(client, admin_auth_headers):
    sorries = load_multiple_sorries_as_json()
    put_sorries(client, admin_auth_headers, sorries)
    put_sorries(client, admin_auth_headers, sorries[:1])

    assert client.get("/sorries/").json()["total"] == 1
    assert client.get("/sorries/stats").json()["total"] == 1


def test_a_retired_sorry_still_resolves_by_id(client, session, admin_auth_headers):
    """The whole point of retiring rather than deleting.

    An agent proves sorry A at commit X. Its repo then advances, so the crawl
    reports a different id for the same unresolved goal and A leaves the set.
    The challenge still has to resolve to A, at A's commit and location.
    """
    sorries = load_multiple_sorries_as_json()
    put_sorries(client, admin_auth_headers, sorries)
    put_sorries(client, admin_auth_headers, sorries[:1])

    session.expire_all()
    retired_id = next(iter(stored_ids(session, retired=True)))

    response = client.get(f"/sorries/{retired_id}")
    assert response.status_code == 200
    assert response.json()["id"] == retired_id


def test_replace_rejects_an_anonymous_caller(client):
    """Unauthenticated this endpoint could retire the entire dataset."""
    response = client.put("/sorries/", json=load_multiple_sorries_as_json())
    assert response.status_code == 401


def test_replace_rejects_a_non_admin_user(client, auth_headers):
    response = client.put(
        "/sorries/", json=load_multiple_sorries_as_json(), headers=auth_headers
    )
    assert response.status_code == 403
