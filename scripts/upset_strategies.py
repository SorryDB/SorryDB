#!/usr/bin/env python3
"""
UpSet plot for comparing which sorries different strategies solve.

Shows intersections between strategies - which sorries are solved uniquely
by each strategy vs. solved by multiple strategies.

Usage:
    uv run --with matplotlib --with upsetplot python3 scripts/upset_strategies.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --strategies claude gemini gpt multi_tactic \
        --subfolder 1000 \
        --output charts/upset_strategies.png
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Set

import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

from upsetplot import UpSet, from_memberships


def discover_experiment_for_strategy(base_dir: Path, strategy: str, subfolder: str) -> Path:
    """
    Discover the experiment directory for a given strategy and subfolder.

    Args:
        base_dir: Base directory containing strategy folders
        strategy: Strategy name (e.g., 'claude', 'gemini')
        subfolder: Subfolder within strategy (e.g., '1000')

    Returns:
        Path to the experiment directory

    Raises:
        SystemExit: If zero or multiple experiments found
    """
    strategy_path = base_dir / strategy / subfolder

    if not strategy_path.exists():
        print(f"Error: Strategy path does not exist: {strategy_path}")
        sys.exit(1)

    # Find all subdirectories containing result.json
    experiment_dirs = [
        d for d in strategy_path.iterdir()
        if d.is_dir() and (d / "result.json").exists()
    ]

    if len(experiment_dirs) == 0:
        print(f"Error: No experiments found in {strategy_path}")
        print("(Looking for subdirectories containing result.json)")
        sys.exit(1)

    if len(experiment_dirs) > 1:
        print(f"Error: Multiple experiments found in {strategy_path}:")
        for d in sorted(experiment_dirs):
            print(f"  - {d.name}")
        print("Please ensure only one experiment exists per strategy/subfolder.")
        sys.exit(1)

    return experiment_dirs[0]


def load_verified_sorry_ids(result_json_path: Path) -> Set[str]:
    """
    Load result.json and return set of sorry IDs where proof_verified is True.

    Args:
        result_json_path: Path to result.json file

    Returns:
        Set of sorry IDs that were verified
    """
    with open(result_json_path, 'r') as f:
        data = json.load(f)

    verified_ids = set()
    for entry in data:
        if entry.get('proof_verified', False):
            sorry_id = entry.get('sorry', {}).get('id')
            if sorry_id:
                verified_ids.add(sorry_id)

    return verified_ids


def generate_upset_plot(strategy_sets: Dict[str, Set[str]], output_path: str):
    """
    Generate an UpSet plot showing intersections between strategy sets.

    Args:
        strategy_sets: Dict mapping strategy name to set of verified sorry IDs
        output_path: Path to save the plot
    """
    # Convert to membership format for upsetplot
    # Each sorry ID maps to a tuple of strategies that solved it
    all_sorry_ids = set()
    for ids in strategy_sets.values():
        all_sorry_ids.update(ids)

    memberships = []
    for sorry_id in all_sorry_ids:
        member_of = tuple(
            strategy for strategy, ids in strategy_sets.items()
            if sorry_id in ids
        )
        memberships.append(member_of)

    # Create the upset data
    upset_data = from_memberships(memberships)

    # Create the plot
    fig = plt.figure(figsize=(12, 8))
    upset = UpSet(
        upset_data,
        subset_size='count',
        show_counts=True,
        sort_by='cardinality',
        sort_categories_by='cardinality'
    )
    upset.plot(fig=fig)

    # Add title
    plt.suptitle('Strategy Comparison: Which Sorries Each Strategy Solves', fontsize=14, fontweight='bold')

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"✓ UpSet plot saved to {output_path}")


def print_summary(strategy_sets: Dict[str, Set[str]]):
    """Print summary statistics about the strategy sets."""
    print("\n" + "="*60)
    print("STRATEGY COMPARISON SUMMARY")
    print("="*60)

    # Individual counts
    print("\nSorries solved by each strategy:")
    for strategy, ids in sorted(strategy_sets.items()):
        print(f"  {strategy}: {len(ids)}")

    # Union (solved by at least one)
    all_solved = set()
    for ids in strategy_sets.values():
        all_solved.update(ids)
    print(f"\nTotal unique sorries solved (by any strategy): {len(all_solved)}")

    # Intersection (solved by all)
    if strategy_sets:
        solved_by_all = set.intersection(*strategy_sets.values())
        print(f"Sorries solved by ALL strategies: {len(solved_by_all)}")

    # Unique to each strategy
    print("\nSorries solved ONLY by each strategy:")
    for strategy, ids in sorted(strategy_sets.items()):
        others = set()
        for other_strategy, other_ids in strategy_sets.items():
            if other_strategy != strategy:
                others.update(other_ids)
        unique = ids - others
        print(f"  {strategy}: {len(unique)}")

    print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description='Generate UpSet plot comparing which sorries different strategies solve'
    )
    parser.add_argument(
        '--base-dir',
        required=True,
        help='Base directory containing strategy folders'
    )
    parser.add_argument(
        '--strategies',
        nargs='+',
        required=True,
        help='List of strategy names to compare (minimum 2)'
    )
    parser.add_argument(
        '--subfolder',
        required=True,
        help='Subfolder within each strategy (e.g., "1000")'
    )
    parser.add_argument(
        '--output',
        default='charts/upset_strategies.png',
        help='Output path for the chart (default: charts/upset_strategies.png)'
    )

    args = parser.parse_args()

    # Validate minimum strategies
    if len(args.strategies) < 2:
        print(f"Error: Need at least 2 strategies to compare, got {len(args.strategies)}")
        sys.exit(1)

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        print(f"Error: Base directory does not exist: {base_dir}")
        sys.exit(1)

    # Discover and load verified sorry IDs for each strategy
    print(f"Loading experiments from {base_dir}...")
    strategy_sets: Dict[str, Set[str]] = {}

    for strategy in args.strategies:
        experiment_dir = discover_experiment_for_strategy(base_dir, strategy, args.subfolder)
        result_json = experiment_dir / "result.json"

        verified_ids = load_verified_sorry_ids(result_json)
        strategy_sets[strategy] = verified_ids

        print(f"  {strategy}: {len(verified_ids)} verified sorries (from {experiment_dir.name})")

    # Print summary
    print_summary(strategy_sets)

    # Generate plot
    generate_upset_plot(strategy_sets, args.output)

    print("✓ Done!")


if __name__ == '__main__':
    main()
