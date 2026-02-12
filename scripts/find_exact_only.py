#!/usr/bin/env python3
"""
Find sorries where only exact? was able to solve them in a multi_tactic experiment.

Usage:
    python scripts/find_exact_only.py <experiment_dir>

Example:
    python scripts/find_exact_only.py intermediate_experiment_outputs_full_reservoir_3_months/multi_tactic/1000/2026-01-21_02-10-29_multi_tactic
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description='Find sorries where only exact? was able to solve them'
    )
    parser.add_argument(
        'experiment_dir',
        help='Path to multi_tactic experiment directory'
    )
    args = parser.parse_args()

    experiment_dir = Path(args.experiment_dir)
    result_json = experiment_dir / 'result.json'

    if not result_json.exists():
        print(f"Error: result.json not found in {experiment_dir}")
        sys.exit(1)

    with open(result_json) as f:
        data = json.load(f)

    # Find entries where exact? is the ONLY successful tactic
    exact_only = []
    for entry in data:
        successful = entry.get('successful_attempts') or []
        if successful == ['exact?']:
            exact_only.append(entry)

    # Print results
    print(f"Sorries solved ONLY by exact?: {len(exact_only)}")
    print()

    for entry in exact_only:
        sorry = entry['sorry']
        goal = sorry['debug_info']['goal'].replace('\n', ' ')
        print(f"  - {sorry['id']}")
        print(f"    Goal: {goal[:80]}...")
        print(f"    URL: {sorry['debug_info']['url']}")
        print()


if __name__ == '__main__':
    main()
