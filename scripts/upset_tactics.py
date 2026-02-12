#!/usr/bin/env python3
"""
UpSet plot for comparing which sorries different tactics solve within multi_tactic strategy.

Shows intersections between tactics - which sorries are solved uniquely
by each tactic vs. solved by multiple tactics.

Usage:
    uv run --with matplotlib --with upsetplot --with pandas python3 scripts/upset_tactics.py \
        intermediate_experiment_outputs_full_reservoir_3_months/multi_tactic/1000/2026-01-13_01-27-45_multi_tactic/result.json \
        --output charts/upset_tactics.png

    # With category coloring:
    uv run --with matplotlib --with upsetplot --with pandas python3 scripts/upset_tactics.py \
        intermediate_experiment_outputs_full_reservoir_3_months/multi_tactic/1000/2026-01-13_01-27-45_multi_tactic/result.json \
        --categories data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir_categories.json \
        --output charts/upset_tactics_by_category.png
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import matplotlib.pyplot as plt
import matplotlib
from matplotlib import cm
matplotlib.use('Agg')

import pandas as pd
from upsetplot import UpSet, from_memberships


def load_verified_by_tactic(result_json_path: Path) -> Tuple[Dict[str, Set[str]], Dict[str, str]]:
    """
    Load result.json and group verified sorry IDs by tactic.

    Args:
        result_json_path: Path to result.json file

    Returns:
        Tuple of:
        - Dict mapping tactic name to set of sorry IDs it solved
        - Dict mapping sorry_id to repo_url (for category lookup)
    """
    with open(result_json_path, 'r') as f:
        data = json.load(f)

    tactic_sets: Dict[str, Set[str]] = {}
    sorry_repos: Dict[str, str] = {}

    for entry in data:
        if entry.get('proof_verified', False):
            sorry_id = entry.get('sorry', {}).get('id')
            successful = entry.get('successful_attempts', [])
            repo_url = entry.get('sorry', {}).get('repo', {}).get('remote', '')

            if sorry_id and successful:
                for tactic in successful:
                    if tactic not in tactic_sets:
                        tactic_sets[tactic] = set()
                    tactic_sets[tactic].add(sorry_id)
                sorry_repos[sorry_id] = repo_url

    return tactic_sets, sorry_repos


def load_categories(categories_path: Path) -> Dict[str, str]:
    """
    Load repo_categories.json and return mapping of repo name -> category.
    """
    with open(categories_path, 'r') as f:
        data = json.load(f)

    return {entry['name']: entry['category'] for entry in data['categories']}


def extract_repo_name(repo_url: str) -> str:
    """Extract owner/repo from GitHub URL."""
    url = repo_url.rstrip('/').removesuffix('.git')
    if url.startswith('https://github.com/'):
        return url.replace('https://github.com/', '')
    return url


def generate_upset_plot(
    tactic_sets: Dict[str, Set[str]],
    output_path: str,
    sorry_categories: Optional[Dict[str, str]] = None
):
    """
    Generate an UpSet plot showing intersections between tactic sets.

    Args:
        tactic_sets: Dict mapping tactic name to set of verified sorry IDs
        output_path: Path to save the plot
        sorry_categories: Optional dict mapping sorry_id -> category for stacked bars
    """
    # Get all unique sorry IDs
    all_sorry_ids = set()
    for ids in tactic_sets.values():
        all_sorry_ids.update(ids)

    tactic_names = list(tactic_sets.keys())

    if sorry_categories is not None:
        # Build DataFrame for stacked bars mode
        rows = []
        for sorry_id in all_sorry_ids:
            row = {
                'sorry_id': sorry_id,
                'category': sorry_categories.get(sorry_id, 'unknown')
            }
            # Add boolean column for each tactic
            for tactic in tactic_names:
                row[tactic] = sorry_id in tactic_sets[tactic]
            rows.append(row)

        df = pd.DataFrame(rows)

        # Set MultiIndex based on tactic membership
        df = df.set_index(tactic_names)

        # Create the plot with stacked bars
        fig = plt.figure(figsize=(14, 8))
        upset = UpSet(
            df,
            subset_size='count',
            show_counts=True,
            sort_by='cardinality',
            sort_categories_by='cardinality',
            intersection_plot_elements=0  # Disable default bars
        )

        # Add stacked bars colored by category
        upset.add_stacked_bars(
            by='category',
            colors=cm.Set2,
            title='',
            elements=10
        )

        upset.plot(fig=fig)

    else:
        # Original mode without categories
        memberships = []
        for sorry_id in all_sorry_ids:
            member_of = tuple(
                tactic for tactic, ids in tactic_sets.items()
                if sorry_id in ids
            )
            memberships.append(member_of)

        # Create the upset data
        upset_data = from_memberships(memberships)

        # Create the plot
        fig = plt.figure(figsize=(14, 8))
        upset = UpSet(
            upset_data,
            subset_size='count',
            show_counts=True,
            sort_by='cardinality',
            sort_categories_by='cardinality'
        )
        upset.plot(fig=fig)

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"✓ UpSet plot saved to {output_path}")


def print_summary(tactic_sets: Dict[str, Set[str]]):
    """Print summary statistics about the tactic sets."""
    print("\n" + "="*60)
    print("TACTIC COMPARISON SUMMARY")
    print("="*60)

    # Individual counts
    print("\nSorries solved by each tactic:")
    for tactic, ids in sorted(tactic_sets.items(), key=lambda x: -len(x[1])):
        print(f"  {tactic}: {len(ids)}")

    # Union (solved by at least one)
    all_solved = set()
    for ids in tactic_sets.values():
        all_solved.update(ids)
    print(f"\nTotal unique sorries solved (by any tactic): {len(all_solved)}")

    # Intersection (solved by all) - only if reasonable number of tactics
    if len(tactic_sets) <= 5 and tactic_sets:
        solved_by_all = set.intersection(*tactic_sets.values())
        print(f"Sorries solved by ALL tactics: {len(solved_by_all)}")

    # Unique to each tactic
    print("\nSorries solved ONLY by each tactic:")
    for tactic, ids in sorted(tactic_sets.items(), key=lambda x: -len(x[1])):
        others = set()
        for other_tactic, other_ids in tactic_sets.items():
            if other_tactic != tactic:
                others.update(other_ids)
        unique = ids - others
        if len(unique) > 0:
            print(f"  {tactic}: {len(unique)}")

    print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description='Generate UpSet plot comparing which sorries different tactics solve within multi_tactic'
    )
    parser.add_argument(
        'result_json',
        help='Path to multi_tactic result.json file'
    )
    parser.add_argument(
        '--output',
        default='charts/upset_tactics.png',
        help='Output path for the chart (default: charts/upset_tactics.png)'
    )
    parser.add_argument(
        '--categories',
        help='Path to repo_categories.json for category-colored stacked bars'
    )
    parser.add_argument(
        '--min-solved',
        type=int,
        default=1,
        help='Only include tactics that solved at least this many sorries (default: 1)'
    )

    args = parser.parse_args()

    result_path = Path(args.result_json)
    if not result_path.exists():
        print(f"Error: Result file does not exist: {result_path}")
        sys.exit(1)

    # Load categories if provided
    categories_map: Optional[Dict[str, str]] = None
    if args.categories:
        categories_path = Path(args.categories)
        if not categories_path.exists():
            print(f"Error: Categories file does not exist: {categories_path}")
            sys.exit(1)
        categories_map = load_categories(categories_path)
        print(f"Loaded {len(categories_map)} repo categories")

    # Load verified sorries grouped by tactic
    print(f"Loading results from {result_path}...")
    tactic_sets, sorry_repos = load_verified_by_tactic(result_path)

    # Filter tactics by minimum solved
    if args.min_solved > 1:
        original_count = len(tactic_sets)
        tactic_sets = {t: ids for t, ids in tactic_sets.items() if len(ids) >= args.min_solved}
        print(f"Filtered from {original_count} to {len(tactic_sets)} tactics (min {args.min_solved} solved)")

    if len(tactic_sets) < 2:
        print(f"Error: Need at least 2 tactics with sufficient solved sorries, got {len(tactic_sets)}")
        sys.exit(1)

    # Print tactic counts
    for tactic, ids in sorted(tactic_sets.items(), key=lambda x: -len(x[1])):
        print(f"  {tactic}: {len(ids)} verified sorries")

    # Build sorry_categories mapping if categories provided
    sorry_categories: Optional[Dict[str, str]] = None
    if categories_map is not None:
        sorry_categories = {}
        for sorry_id, repo_url in sorry_repos.items():
            repo_name = extract_repo_name(repo_url)
            sorry_categories[sorry_id] = categories_map.get(repo_name, 'unknown')

    # Print summary
    print_summary(tactic_sets)

    # Generate plot
    generate_upset_plot(tactic_sets, args.output, sorry_categories)

    print("✓ Done!")


if __name__ == '__main__':
    main()
