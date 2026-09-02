"""Tests for REPL tag selection.

The REPL does not tag every Lean patch release, so extraction has to fall back
to a nearby tag. The rule is deliberately narrow: never across a minor version,
because a mismatched REPL risks subtly wrong goals and bad data in the database
is worse than a repo we skip.
"""

import pytest

from sorrydb.utils.lean_version import (
    parse_lean_version,
    parse_toolchain_version,
    select_repl_tag,
)

# A slice of the real leanprover-community/repl tags, including the v4.33.0 to
# v4.34.0-rc1 gap that made LSpec on v4.33.1 fail.
REPL_TAGS = [
    "v4.11.0",
    "v4.22.0",
    "v4.23.0-rc1",
    "v4.23.0-rc2",
    "v4.25.0",
    "v4.25.1",
    "v4.32.0-rc1",
    "v4.32.0",
    "v4.33.0-rc1",
    "v4.33.0-rc2",
    "v4.33.0",
    "v4.34.0-rc1",
    "v4.34.0-rc2",
]


def test_exact_match_wins():
    assert select_repl_tag("v4.33.0", REPL_TAGS) == "v4.33.0"
    assert select_repl_tag("v4.34.0-rc1", REPL_TAGS) == "v4.34.0-rc1"


def test_falls_back_to_nearest_tag_in_the_same_minor():
    # the case that motivated this: there is no v4.33.1
    assert select_repl_tag("v4.33.1", REPL_TAGS) == "v4.33.0"
    assert select_repl_tag("v4.25.2", REPL_TAGS) == "v4.25.1"


def test_release_falls_back_to_its_own_release_candidate():
    # v4.23.0 is not tagged, and rc2 must beat rc1 and must beat v4.22.0
    assert select_repl_tag("v4.23.0", REPL_TAGS) == "v4.23.0-rc2"


def test_never_falls_back_across_a_minor_version():
    # v4.13 has no tags at all, and v4.11.0 must not be used for it
    assert select_repl_tag("v4.13.0", REPL_TAGS) is None
    # nothing at or below in v4.24 either, even though v4.23.0-rc2 is close
    assert select_repl_tag("v4.24.0", REPL_TAGS) is None
    # and never a newer tag from the same minor
    assert select_repl_tag("v4.33.0-rc1", ["v4.33.0"]) is None


def test_nightly_toolchains_have_no_usable_tag():
    assert select_repl_tag("nightly-2022-12-23", REPL_TAGS) is None


def test_parse_toolchain_version():
    assert parse_toolchain_version("leanprover/lean4:v4.17.0\n") == "v4.17.0"
    assert parse_toolchain_version("leanprover/lean4:nightly-2022-12-23") == (
        "nightly-2022-12-23"
    )
    assert parse_toolchain_version("garbage") is None
    assert parse_toolchain_version("leanprover/lean4:") is None


def test_parse_lean_version_orders_releases_after_their_candidates():
    assert parse_lean_version("v4.23.0") > parse_lean_version("v4.23.0-rc2")
    assert parse_lean_version("v4.23.0-rc2") > parse_lean_version("v4.23.0-rc1")
    with pytest.raises(ValueError):
        parse_lean_version("nightly-2022-12-23")
