#!/usr/bin/env python3
"""Build a sorry file for verifying a prover submission on MorphCloud.

The submission carries the full sorry record for each entry, but
`run_morphcloud_agent` expects a `{"sorries": [...]}` envelope, so this pulls
those records back out. Sampling is stratified by (repo, commit) because that
pair is what a MorphCloud snapshot is built for -- sampling at random spreads a
handful of sorries over as many repo builds, which is the slow part.

Usage:
    python scripts/prepare_submission_verification.py aleph_prover_submission.json \
        --limit 3 --output sample_sorries.json
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path, help="Path to the submission JSON")
    parser.add_argument("--output", type=Path, required=True, help="Where to write the sorry file")
    parser.add_argument("--limit", type=int, help="Take at most this many sorries")
    parser.add_argument("--repo", help="Only sorries whose repo remote contains this string")
    parser.add_argument("--lean-version", help="Only sorries pinned to this Lean version")
    parser.add_argument(
        "--per-repo",
        type=int,
        default=0,
        help="Take at most this many sorries per (repo, commit); 0 means no cap",
    )
    args = parser.parse_args()

    entries = json.loads(args.submission.read_text())
    sorries = [e["sorry"] for e in entries]

    if args.repo:
        sorries = [s for s in sorries if args.repo in s["repo"]["remote"]]
    if args.lean_version:
        sorries = [s for s in sorries if s["repo"]["lean_version"] == args.lean_version]

    if args.per_repo:
        seen = defaultdict(int)
        capped = []
        for s in sorries:
            key = (s["repo"]["remote"], s["repo"]["commit"])
            if seen[key] < args.per_repo:
                seen[key] += 1
                capped.append(s)
        sorries = capped

    if args.limit:
        sorries = sorries[: args.limit]

    args.output.write_text(json.dumps({"sorries": sorries}, indent=2, ensure_ascii=False))

    repos = {(s["repo"]["remote"], s["repo"]["commit"]) for s in sorries}
    print(f"Wrote {len(sorries)} sorries to {args.output}")
    print(f"Spanning {len(repos)} (repo, commit) pairs -> that many snapshot builds")
    for remote, commit in sorted(repos):
        n = sum(
            1 for s in sorries
            if s["repo"]["remote"] == remote and s["repo"]["commit"] == commit
        )
        print(f"  {n:3d}  {remote}@{commit[:12]}  ({[s['repo']['lean_version'] for s in sorries if s['repo']['remote'] == remote][0]})")


if __name__ == "__main__":
    main()
