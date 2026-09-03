"""Lean toolchain versions, and which REPL tag can handle them.

Pure logic, no IO, so the selection rules can be tested directly.
"""

import re

VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-rc(\d+))?$")


def parse_lean_version(v: str) -> tuple[int, int, int, int]:
    """Parse v4.18.0 or v4.18.0-rc2 -> (4, 18, 0, rc_num). RC None becomes 9999.

    The 9999 puts a release after all of its release candidates, so the tuples
    sort the way versions do.
    """
    m = VERSION_RE.match(v)
    if not m:
        raise ValueError(f"Invalid version: {v}")
    return (
        int(m.group(1)),
        int(m.group(2)),
        int(m.group(3)),
        int(m.group(4)) if m.group(4) else 9999,
    )


def parse_toolchain_version(toolchain: str) -> str | None:
    """Version out of the contents of a lean-toolchain file.

    "leanprover/lean4:v4.17.0" -> "v4.17.0". None when there is no version part.
    """
    _, colon, version = toolchain.strip().partition(":")
    version = version.strip()
    return version if colon and version else None


def select_repl_tag(version: str, available_tags) -> str | None:
    """Pick the REPL tag to use for a Lean toolchain version.

    An exact match always wins. Otherwise the highest tag at or below the
    requested version that shares its major and minor, because the REPL does not
    tag every Lean patch release: there is no v4.33.1, only v4.33.0.

    Never falls back across a minor version. A v4.11 REPL against a v4.13
    toolchain risks subtly wrong goals, and silently bad data in the database is
    worse than a repo we skip. Returns None when there is no usable tag, which
    includes nightly toolchains, since those do not parse as versions at all.
    """
    tags = set(available_tags)
    if version in tags:
        return version

    try:
        wanted = parse_lean_version(version)
    except ValueError:
        return None

    best = None
    best_parsed = None
    for tag in tags:
        try:
            parsed = parse_lean_version(tag)
        except ValueError:
            continue
        if parsed[:2] != wanted[:2]:  # same major and minor only
            continue
        if parsed > wanted:
            continue
        if best_parsed is None or parsed > best_parsed:
            best, best_parsed = tag, parsed

    return best
