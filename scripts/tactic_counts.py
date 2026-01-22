#!/usr/bin/env python3
"""
Bar chart showing how many sorries each tactic solves in a multi_tactic experiment.

Usage:
    uv run --with matplotlib python3 scripts/tactic_counts.py \
        intermediate_experiment_outputs_full_reservoir_3_months/multi_tactic/1000/2026-01-21_02-10-29_multi_tactic/result.json \
        --output charts/tactic_counts.png
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Set

import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')


def load_tactic_sets(result_json_path: Path) -> Dict[str, Set[str]]:
    """
    Load result.json and group sorry IDs by tactic.

    Args:
        result_json_path: Path to result.json file

    Returns:
        Dict mapping tactic name to set of sorry IDs it solved
    """
    with open(result_json_path, 'r') as f:
        data = json.load(f)

    tactic_sets: Dict[str, Set[str]] = {}

    for entry in data:
        if entry.get('proof_verified', False):
            sorry_id = entry.get('sorry', {}).get('id')
            successful = entry.get('successful_attempts', [])

            if sorry_id and successful:
                for tactic in successful:
                    if tactic not in tactic_sets:
                        tactic_sets[tactic] = set()
                    tactic_sets[tactic].add(sorry_id)

    return tactic_sets


def generate_bar_chart(tactic_counts: Dict[str, int], total_unique: int, output_path: str, title: str = None):
    """
    Generate a bar chart showing tactic solve counts with a total bar.

    Args:
        tactic_counts: Dict mapping tactic name to count
        total_unique: Total unique sorries solved (across all tactics)
        output_path: Path to save the chart
        title: Optional custom title
    """
    # Sort by count descending
    sorted_tactics = sorted(tactic_counts.items(), key=lambda x: -x[1])
    tactics = [t[0] for t in sorted_tactics] + ['Total']
    counts = [t[1] for t in sorted_tactics] + [total_unique]

    # Create figure
    fig, ax = plt.subplots(figsize=(12, 6))

    # Create bars with different color for Total
    colors = ['steelblue'] * (len(tactics) - 1) + ['darkgreen']
    bars = ax.bar(range(len(tactics)), counts, color=colors, edgecolor='black', linewidth=0.5)

    # Add count labels on bars
    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                str(count), ha='center', va='bottom', fontsize=10, fontweight='bold')

    # Customize axes
    ax.set_xticks(range(len(tactics)))
    ax.set_xticklabels(tactics, rotation=45, ha='right', fontsize=10)
    ax.set_ylabel('Sorries Solved', fontsize=12)
    ax.set_xlabel('Tactic', fontsize=12)

    # Title
    if title:
        ax.set_title(title, fontsize=14, fontweight='bold')
    else:
        ax.set_title('Sorries Solved by Each Tactic', fontsize=14, fontweight='bold')

    # Add grid
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    ax.set_axisbelow(True)

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Chart saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate bar chart of sorries solved by each tactic'
    )
    parser.add_argument(
        'result_json',
        help='Path to multi_tactic result.json file'
    )
    parser.add_argument(
        '--output',
        default='charts/tactic_counts.png',
        help='Output path for the chart (default: charts/tactic_counts.png)'
    )
    parser.add_argument(
        '--title',
        help='Custom chart title'
    )

    args = parser.parse_args()

    result_path = Path(args.result_json)
    if not result_path.exists():
        print(f"Error: Result file does not exist: {result_path}")
        sys.exit(1)

    print(f"Loading results from {result_path}...")
    tactic_sets = load_tactic_sets(result_path)

    if not tactic_sets:
        print("Error: No verified proofs found in result file")
        sys.exit(1)

    # Compute counts and total unique
    tactic_counts = {tactic: len(ids) for tactic, ids in tactic_sets.items()}
    all_sorries: Set[str] = set()
    for ids in tactic_sets.values():
        all_sorries.update(ids)
    total_unique = len(all_sorries)

    # Print summary
    print("\nTactic solve counts:")
    for tactic, count in sorted(tactic_counts.items(), key=lambda x: -x[1]):
        print(f"  {tactic}: {count}")

    print(f"\nTotal unique sorries solved: {total_unique}")

    # Generate chart
    generate_bar_chart(tactic_counts, total_unique, args.output, args.title)
    print("Done!")


if __name__ == '__main__':
    main()
