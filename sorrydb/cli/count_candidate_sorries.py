"""On-VM candidate check for the MorphCloud crawler.

Counts the files that could contain sorries using the same
get_potential_sorry_files that the extraction itself uses, and writes a marker
file when there are any. The crawler's later build steps test for that marker
and no-op without it, so a repo with nothing to extract does not pay for
`lake exe cache get` or `lake build`.

Deliberately the real predicate rather than a grep for "sorry": mathlib's
candidate set is empty on master because get_potential_sorry_files intersects
the diffs against origin/master, not because the string is absent.
"""

import argparse
from pathlib import Path

from ..database.process_sorries import get_potential_sorry_files, is_mathlib_repo

DEFAULT_REPO_PATH = "/root/repo"
DEFAULT_MARKER_PATH = "/root/candidate_sorries.marker"


if __name__ == "__main__":
    argparser = argparse.ArgumentParser(
        description="Count the files that could contain sorries, and mark the result"
    )
    argparser.add_argument(
        "--repo-url", type=str, required=True, help="Git remote URL of the repository"
    )
    argparser.add_argument(
        "--repo-path",
        type=str,
        default=DEFAULT_REPO_PATH,
        help=f"Path to the checkout (default: {DEFAULT_REPO_PATH})",
    )
    argparser.add_argument(
        "--marker",
        type=str,
        default=DEFAULT_MARKER_PATH,
        help=f"Marker to write when there are candidates (default: {DEFAULT_MARKER_PATH})",
    )
    args = argparser.parse_args()

    candidates = get_potential_sorry_files(
        Path(args.repo_path), is_mathlib=is_mathlib_repo(args.repo_url)
    )

    # The marker holds the file list, which is free and useful when debugging a
    # skipped build. It lives outside the checkout so it cannot dirty the git
    # tree that get_potential_sorry_files diffs against.
    marker = Path(args.marker)
    if candidates:
        marker.write_text("\n".join(str(path) for path in candidates))
    elif marker.exists():
        marker.unlink()

    # Parsed by the crawler's candidate check step
    print(f"candidate_files={len(candidates)}")
