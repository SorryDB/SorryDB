import copy

import pytest

from sorrydb.leaderboard.model.agent import Agent
from sorrydb.leaderboard.model.challenge import Challenge, ChallengeStatus
from tests.leaderboard.test_sorries import load_single_sorry_as_json

REPO_A = "https://github.com/example/repoA"
REPO_B = "https://github.com/example/repoB"
REPO_C = "https://github.com/example/repoC"
V16 = "v4.16.0"
V17 = "v4.17.0"

# label, remote, lean_version, blame_date, inclusion_date
SEED = [
    ("s00", REPO_A, V16, "2024-01-05", "2024-05-01"),
    ("s01", REPO_A, V16, "2024-01-10", "2024-05-02"),
    ("s02", REPO_A, V16, "2024-02-05", "2024-05-03"),
    ("s03", REPO_A, V17, "2024-02-10", "2024-05-04"),
    ("s04", REPO_A, V17, "2024-03-05", "2024-05-05"),
    ("s05", REPO_B, V16, "2024-01-15", "2024-05-06"),
    ("s06", REPO_B, V16, "2024-02-15", "2024-06-01"),
    ("s07", REPO_B, V17, "2024-03-10", "2024-06-02"),
    ("s08", REPO_B, V17, "2024-03-15", "2024-06-03"),
    ("s09", REPO_C, V16, "2024-01-20", "2024-06-04"),
    ("s10", REPO_C, V16, "2024-02-20", "2024-06-05"),
    ("s11", REPO_C, V17, "2024-03-20", "2024-06-06"),
]

SOLVED = ["s00", "s05", "s11"]
# a challenge that did not succeed must not make its sorry count as solved
FAILED = "s01"


def build_sorry(label, remote, lean_version, blame_date, inclusion_date) -> dict:
    """A sorry payload for the seed. Sorry ids are content hashes assigned by the
    API, so the label only exists on the test side."""
    sorry = copy.deepcopy(load_single_sorry_as_json())
    sorry["repo"]["remote"] = remote
    sorry["repo"]["lean_version"] = lean_version
    sorry["metadata"]["blame_date"] = f"{blame_date}T00:00:00+00:00"
    sorry["metadata"]["inclusion_date"] = f"{inclusion_date}T00:00:00+00:00"
    return sorry


class Seeded:
    """Translates between the seed labels and the ids the API assigned."""

    def __init__(self, id_by_label: dict, agent: Agent):
        self.id_by_label = id_by_label
        self.label_by_id = {v: k for k, v in id_by_label.items()}
        self.agent = agent

    def id(self, label: str) -> str:
        return self.id_by_label[label]

    def labels(self, response) -> list[str]:
        return [self.label_by_id[item["id"]] for item in response.json()["items"]]


@pytest.fixture(name="seeded")
def seeded_fixture(client, session, test_user):
    """Post the seed sorries and attach challenges directly to the database."""
    response = client.post("/sorries/", json=[build_sorry(*row) for row in SEED])
    assert response.status_code == 201

    # the batch POST response does not carry the ids, so read them back from the
    # list endpoint and key them on blame_date, which is unique within the seed
    listed = client.get("/sorries/", params={"limit": len(SEED)}).json()["items"]
    assert len(listed) == len(SEED)
    id_by_blame_date = {item["blame_date"][:10]: item["id"] for item in listed}
    id_by_label = {row[0]: id_by_blame_date[row[3]] for row in SEED}
    assert len(set(id_by_label.values())) == len(SEED), "seed ids collided"

    agent = Agent(name="seed agent", user_id=test_user["id"])
    session.add(agent)
    session.commit()

    for label in SOLVED:
        session.add(
            Challenge(
                sorry_id=id_by_label[label],
                agent_id=agent.id,
                status=ChallengeStatus.SUCCESS,
                submission="rfl",
            )
        )
    session.add(
        Challenge(
            sorry_id=id_by_label[FAILED],
            agent_id=agent.id,
            status=ChallengeStatus.FAILED,
        )
    )
    session.commit()

    return Seeded(id_by_label, agent)


def test_list_returns_first_page_and_total(client, seeded):
    response = client.get("/sorries/", params={"limit": 5, "offset": 0})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == len(SEED)
    assert body["limit"] == 5
    assert body["offset"] == 0
    assert len(body["items"]) == 5
    # the default sort is inclusion_date descending
    assert seeded.labels(response) == ["s11", "s10", "s09", "s08", "s07"]


def test_list_last_page_is_short(client, seeded):
    response = client.get("/sorries/", params={"limit": 5, "offset": 10})
    assert response.status_code == 200
    assert response.json()["total"] == len(SEED)
    assert seeded.labels(response) == ["s01", "s00"]


def test_list_offset_past_the_end_is_empty(client, seeded):
    response = client.get("/sorries/", params={"limit": 5, "offset": 12})
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == len(SEED)


def test_list_pages_cover_every_sorry_exactly_once(client, seeded):
    seen = []
    for offset in range(0, len(SEED), 5):
        seen += seeded.labels(
            client.get("/sorries/", params={"limit": 5, "offset": offset})
        )
    assert sorted(seen) == [row[0] for row in SEED]


def test_paging_is_stable_when_sorries_share_an_inclusion_date(client):
    """The nightly job gives a whole batch the same inclusion_date."""
    same_date = [
        build_sorry(f"t{i}", REPO_A, V16, f"2024-04-{i + 1:02d}", "2024-07-01")
        for i in range(3)
    ]
    assert client.post("/sorries/", json=same_date).status_code == 201

    seen = []
    for offset in range(3):
        body = client.get("/sorries/", params={"limit": 1, "offset": offset}).json()
        seen += [item["id"] for item in body["items"]]
    assert len(set(seen)) == 3


def test_limit_and_offset_are_bounded(client, seeded):
    assert client.get("/sorries/", params={"limit": 201}).status_code == 422
    assert client.get("/sorries/", params={"limit": 0}).status_code == 422
    assert client.get("/sorries/", params={"offset": -1}).status_code == 422


def test_filter_by_remote(client, seeded):
    response = client.get("/sorries/", params={"remote": REPO_A})
    assert response.json()["total"] == 5
    assert sorted(seeded.labels(response)) == ["s00", "s01", "s02", "s03", "s04"]


def test_filter_by_lean_version(client, seeded):
    response = client.get("/sorries/", params={"lean_version": V17})
    assert response.json()["total"] == 5
    assert sorted(seeded.labels(response)) == ["s03", "s04", "s07", "s08", "s11"]


def test_filter_by_blame_date_range(client, seeded):
    response = client.get(
        "/sorries/",
        params={
            "blame_date_from": "2024-02-01T00:00:00+00:00",
            "blame_date_to": "2024-02-28T00:00:00+00:00",
        },
    )
    assert response.json()["total"] == 4
    assert sorted(seeded.labels(response)) == ["s02", "s03", "s06", "s10"]


def test_filters_combine(client, seeded):
    response = client.get("/sorries/", params={"remote": REPO_A, "lean_version": V17})
    assert response.json()["total"] == 2
    assert sorted(seeded.labels(response)) == ["s03", "s04"]


def test_filter_solved(client, seeded):
    response = client.get("/sorries/", params={"solved": True})
    assert response.json()["total"] == len(SOLVED)
    assert sorted(seeded.labels(response)) == SOLVED
    assert all(item["solved"] for item in response.json()["items"])


def test_filter_unsolved_includes_a_sorry_with_a_failed_challenge(client, seeded):
    response = client.get("/sorries/", params={"solved": False, "limit": 200})
    assert response.json()["total"] == len(SEED) - len(SOLVED)
    assert FAILED in seeded.labels(response)
    assert not any(item["solved"] for item in response.json()["items"])


def test_sort_by_blame_date_ascending(client, seeded):
    response = client.get(
        "/sorries/",
        params={"sort_by": "blame_date", "sort_order": "asc", "limit": 3},
    )
    assert seeded.labels(response) == ["s00", "s01", "s05"]


def test_sort_by_inclusion_date_ascending(client, seeded):
    response = client.get(
        "/sorries/",
        params={"sort_by": "inclusion_date", "sort_order": "asc", "limit": 3},
    )
    assert seeded.labels(response) == ["s00", "s01", "s02"]


def test_detail_includes_challenge_history(client, seeded):
    response = client.get(f"/sorries/{seeded.id('s00')}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == seeded.id("s00")
    assert body["remote"] == REPO_A
    assert body["lean_version"] == V16
    assert body["solved"] is True
    assert len(body["challenges"]) == 1
    challenge = body["challenges"][0]
    assert challenge["status"] == "SUCCESS"
    assert challenge["agent_name"] == "seed agent"
    assert challenge["agent_id"] == seeded.agent.id
    assert challenge["submission"] == "rfl"


def test_detail_of_a_sorry_with_only_a_failed_challenge(client, seeded):
    body = client.get(f"/sorries/{seeded.id(FAILED)}").json()
    assert body["solved"] is False
    assert [c["status"] for c in body["challenges"]] == ["FAILED"]


def test_detail_of_unattempted_sorry_has_no_challenges(client, seeded):
    body = client.get(f"/sorries/{seeded.id('s02')}").json()
    assert body["solved"] is False
    assert body["challenges"] == []


def test_detail_of_unknown_sorry_is_404(client, seeded):
    assert client.get("/sorries/does-not-exist").status_code == 404


def test_stats_counts_match_the_fixture(client, seeded):
    response = client.get("/sorries/stats")
    assert response.status_code == 200
    stats = response.json()

    assert stats["total"] == len(SEED)
    assert stats["solved"] == len(SOLVED)
    assert stats["unsolved"] == len(SEED) - len(SOLVED)

    assert stats["by_remote"] == [
        {"remote": REPO_A, "count": 5},
        {"remote": REPO_B, "count": 4},
        {"remote": REPO_C, "count": 3},
    ]
    assert stats["by_lean_version"] == [
        {"lean_version": V16, "count": 7},
        {"lean_version": V17, "count": 5},
    ]
    assert stats["by_blame_month"] == [
        {"month": "2024-01", "count": 4},
        {"month": "2024-02", "count": 4},
        {"month": "2024-03", "count": 4},
    ]
    assert stats["by_inclusion_month"] == [
        {"month": "2024-05", "count": 6},
        {"month": "2024-06", "count": 6},
    ]


def test_stats_on_an_empty_database(client):
    stats = client.get("/sorries/stats").json()
    assert stats == {
        "total": 0,
        "solved": 0,
        "unsolved": 0,
        "by_remote": [],
        "by_lean_version": [],
        "by_blame_month": [],
        "by_inclusion_month": [],
    }


def test_filter_options(client, seeded):
    options = client.get("/sorries/filter-options").json()
    assert options["remotes"] == [REPO_A, REPO_B, REPO_C]
    assert options["lean_versions"] == [V16, V17]


def test_filter_options_on_an_empty_database(client):
    assert client.get("/sorries/filter-options").json() == {
        "remotes": [],
        "lean_versions": [],
    }


BLANKABLE_PARAMS = [
    "limit",
    "offset",
    "remote",
    "lean_version",
    "blame_date_from",
    "blame_date_to",
    "solved",
    "sort_by",
    "sort_order",
]


@pytest.mark.parametrize("param", BLANKABLE_PARAMS)
def test_a_blank_parameter_means_no_filter(client, seeded, param):
    """A filter form that submits an empty field should not filter on ""."""
    response = client.get("/sorries/", params={param: ""})
    assert response.status_code == 200
    assert response.json()["total"] == len(SEED)


def test_a_form_submitting_every_field_blank(client, seeded):
    response = client.get("/sorries/", params={p: "" for p in BLANKABLE_PARAMS})
    assert response.status_code == 200
    assert response.json()["total"] == len(SEED)
    # blank sort parameters fall back to the documented defaults
    assert seeded.labels(response)[:3] == ["s11", "s10", "s09"]


def test_detail_survives_a_challenge_with_no_status(client, session, seeded):
    """challenge.status is a nullable column, so the response must allow null."""
    challenge = Challenge(
        sorry_id=seeded.id("s02"), agent_id=seeded.agent.id, status=None
    )
    session.add(challenge)
    session.commit()

    response = client.get(f"/sorries/{seeded.id('s02')}")
    assert response.status_code == 200
    assert [c["status"] for c in response.json()["challenges"]] == [None]
    assert response.json()["solved"] is False

    # the admin views render a challenge through __str__
    assert "no status" in str(challenge)
