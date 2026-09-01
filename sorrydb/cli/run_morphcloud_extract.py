"""On-VM entrypoint for the MorphCloud crawler.

Extracts the sorries of a single repository at a single commit and writes them
to a JSON file, which morphcloud_crawler downloads. The crawler has already
cloned and built the repository into `--lean-data`, so prepare_and_process_lean_repo
reuses that checkout instead of building from scratch.
"""

import argparse
import json
import logging
from pathlib import Path

from ..database.process_sorries import prepare_and_process_lean_repo
from ..database.sorry import SorryJSONEncoder

DEFAULT_LEAN_DATA = "/root/lean_data"
DEFAULT_OUTPUT_PATH = "/root/extract_result.json"


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    argparser = argparse.ArgumentParser(
        description="Extract the sorries of one repository at one commit"
    )
    argparser.add_argument(
        "--repo-url", type=str, required=True, help="Git remote URL of the repository"
    )
    argparser.add_argument(
        "--branch", type=str, required=True, help="Branch the commit belongs to"
    )
    argparser.add_argument(
        "--commit", type=str, required=True, help="Commit SHA to extract sorries from"
    )
    argparser.add_argument(
        "--lean-data",
        type=str,
        default=DEFAULT_LEAN_DATA,
        help=f"Directory holding the prebuilt checkout (default: {DEFAULT_LEAN_DATA})",
    )
    argparser.add_argument(
        "--output-path",
        type=str,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Path to write the result JSON file (default: {DEFAULT_OUTPUT_PATH})",
    )
    args = argparser.parse_args()

    logger.info(
        f"Extracting sorries from {args.repo_url} at {args.commit} (branch {args.branch})"
    )

    results = prepare_and_process_lean_repo(
        repo_url=args.repo_url,
        lean_data=Path(args.lean_data),
        branch=args.branch,
        commit_sha=args.commit,
    )

    with open(args.output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, cls=SorryJSONEncoder, ensure_ascii=False)

    logger.info(f"Wrote {len(results['sorries'])} sorries to {args.output_path}")
