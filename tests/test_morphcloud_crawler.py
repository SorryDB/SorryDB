"""Tests for the crawler's orphan identification.

The MorphCloud SDK cannot be called from tests, so this covers the predicate
that decides which instances the sweeper is allowed to stop. A mistake here
stops someone's running agent experiment, which is why it is the part with a
test.
"""

from types import SimpleNamespace

from sorrydb.runners.morphcloud_crawler import (
    CRAWLER_ROLE,
    CRAWLER_ROLE_KEY,
    stale_crawler_instances,
)

NOW = 1_800_000_000.0
HOUR = 3600
MIN_AGE = 2400


def _instance(name, age_seconds, metadata):
    return SimpleNamespace(
        id=name, created=NOW - age_seconds, metadata=dict(metadata)
    )


def test_stale_crawler_instances_selects_only_our_old_ones():
    stale_crawler = _instance("stale-crawler", 11 * HOUR, {CRAWLER_ROLE_KEY: CRAWLER_ROLE})
    also_stale = _instance("also-stale", MIN_AGE, {CRAWLER_ROLE_KEY: CRAWLER_ROLE})

    instances = [
        stale_crawler,
        also_stale,
        # still in use by a run in progress, younger than the threshold
        _instance("fresh-crawler", 60, {CRAWLER_ROLE_KEY: CRAWLER_ROLE}),
        # the agent runner's experiments, old but not ours to touch
        _instance(
            "agent-run",
            11 * HOUR,
            {"name": "mathlib4_abc123_rfl_id0", "sorry_id": "id0"},
        ),
        # untagged, could be anyone's, including the leak that started all this
        _instance("untagged-old", 24 * HOUR, {}),
        # a different sorrydb role, not the crawler
        _instance("other-role", 24 * HOUR, {CRAWLER_ROLE_KEY: "agent"}),
    ]

    selected = stale_crawler_instances(instances, NOW, MIN_AGE)

    assert [i.id for i in selected] == ["stale-crawler", "also-stale"]


def test_stale_crawler_instances_selects_nothing_without_our_tag():
    instances = [
        _instance("agent-run", 48 * HOUR, {"name": "some_experiment"}),
        _instance("untagged", 48 * HOUR, {}),
    ]

    assert stale_crawler_instances(instances, NOW, MIN_AGE) == []


def test_crawler_client_tags_the_instances_abuild_starts():
    """Snapshot.abuild reaches its instance through client.instances.astart.

    That indirection is the only seam for putting a TTL and our tag on the build
    VM, so assert the override is actually on the path abuild uses. Constructing
    a client makes no network call.
    """
    from morphcloud.api import MorphCloudClient

    from sorrydb.runners.morphcloud_crawler import (
        INSTANCE_TTL_SECONDS,
        _CrawlerInstanceAPI,
        _CrawlerMorphClient,
    )

    client = _CrawlerMorphClient(api_key="test-key")

    # what abuild does: self._api._client.instances.astart(...)
    assert isinstance(client.snapshots._client.instances, _CrawlerInstanceAPI)
    assert isinstance(client, MorphCloudClient)

    metadata, ttl_seconds, ttl_action = client.instances._defaults(None, None, None)
    assert metadata == {CRAWLER_ROLE_KEY: CRAWLER_ROLE}
    assert ttl_seconds == INSTANCE_TTL_SECONDS
    assert ttl_action == "stop"

    # an explicit TTL and extra metadata are preserved, and still tagged
    metadata, ttl_seconds, _ = client.instances._defaults({"name": "n"}, 99, None)
    assert metadata == {"name": "n", CRAWLER_ROLE_KEY: CRAWLER_ROLE}
    assert ttl_seconds == 99
