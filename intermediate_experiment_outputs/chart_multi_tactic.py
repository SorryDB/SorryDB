#!/usr/bin/env python3
"""
Generate bar chart showing tactic success by repository category.

Takes a multi_tactic result.json and creates a grouped bar chart showing
how many sorries each tactic solved within each repository category.

Usage:
    python chart_multi_tactic.py result.json --categories repo_categories.json --output chart.png
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict

import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')


def load_results(file_path: str) -> list:
    """Load result.json file."""
    with open(file_path, 'r') as f:
        data = json.load(f)
    print(f"✓ Loaded {len(data)} entries from {file_path}")
    return data


def load_categories(file_path: str) -> dict:
    """Load repo_categories.json and return mapping of repo name -> category."""
    with open(file_path, 'r') as f:
        data = json.load(f)
    categories = {entry['name']: entry['category'] for entry in data['categories']}
    print(f"✓ Loaded {len(categories)} repo categories from {file_path}")
    return categories


def extract_repo_name(url: str) -> str:
    """Extract owner/repo from GitHub URL."""
    url = url.rstrip('/').removesuffix('.git')
    if url.startswith('https://github.com/'):
        return url.replace('https://github.com/', '')
    return url


def aggregate_by_category_and_strategy(results: list, categories: dict) -> dict:
    """
    Aggregate verified counts by category and strategy.

    Returns: {category: {strategy: verified_count}}
    """
    stats = defaultdict(lambda: defaultdict(int))
    unknown_repos = set()

    for entry in results:
        if not entry.get('proof_verified'):
            continue

        repo_url = entry['sorry']['repo']['remote']
        repo_name = extract_repo_name(repo_url)
        category = categories.get(repo_name, 'unknown')
        strategy = entry.get('strategy_name', 'unknown')

        if category == 'unknown':
            unknown_repos.add(repo_name)

        stats[category][strategy] += 1

    if unknown_repos:
        print(f"⚠ Warning: {len(unknown_repos)} repos not found in categories file")

    return dict(stats)


def generate_chart(stats: dict, output_path: str):
    """Generate grouped bar chart."""
    # Get all categories and strategies
    categories = sorted(stats.keys())
    all_strategies = set()
    for cat_stats in stats.values():
        all_strategies.update(cat_stats.keys())
    strategies = sorted(all_strategies)

    # Prepare data
    n_categories = len(categories)
    n_strategies = len(strategies)

    print(f"Categories: {categories}")
    print(f"Strategies: {strategies}")

    # Create figure
    fig, ax = plt.subplots(figsize=(12, 6))

    # Bar positioning
    x = range(n_categories)
    width = 0.8 / n_strategies

    # Colors
    colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6',
              '#1abc9c', '#e67e22', '#95a5a6', '#34495e', '#16a085', '#d35400']

    # Create bars for each strategy
    for i, strategy in enumerate(strategies):
        offset = (i - n_strategies/2 + 0.5) * width
        counts = [stats.get(cat, {}).get(strategy, 0) for cat in categories]
        bars = ax.bar([pos + offset for pos in x], counts, width,
                     label=strategy, alpha=0.8, color=colors[i % len(colors)])

        # Add value labels
        for bar, count in zip(bars, counts):
            if count > 0:
                ax.text(bar.get_x() + bar.get_width()/2., bar.get_height(),
                       f'{count}', ha='center', va='bottom', fontsize=7)

    # Customize
    ax.set_xlabel('Repository Category', fontsize=12)
    ax.set_ylabel('Verified Sorries', fontsize=12)
    ax.set_title('Verified Sorries by Category and Tactic', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=10)
    ax.legend(fontsize=9, loc='upper right')
    ax.grid(axis='y', alpha=0.3, linestyle='--')

    plt.tight_layout()

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"✓ Chart saved to {output_path}")


def print_summary(stats: dict):
    """Print summary table to console."""
    print("\n" + "="*60)
    print("SUMMARY: Verified Sorries by Category and Tactic")
    print("="*60)

    # Get all strategies
    all_strategies = set()
    for cat_stats in stats.values():
        all_strategies.update(cat_stats.keys())
    strategies = sorted(all_strategies)

    # Print header
    header = f"{'Category':<15}"
    for s in strategies:
        header += f" {s:>8}"
    header += f" {'Total':>8}"
    print(header)
    print("-" * len(header))

    # Print rows
    grand_total = 0
    strategy_totals = defaultdict(int)

    for category in sorted(stats.keys()):
        row = f"{category:<15}"
        cat_total = 0
        for s in strategies:
            count = stats[category].get(s, 0)
            row += f" {count:>8}"
            cat_total += count
            strategy_totals[s] += count
        row += f" {cat_total:>8}"
        grand_total += cat_total
        print(row)

    # Print totals row
    print("-" * len(header))
    totals_row = f"{'TOTAL':<15}"
    for s in strategies:
        totals_row += f" {strategy_totals[s]:>8}"
    totals_row += f" {grand_total:>8}"
    print(totals_row)
    print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description='Generate bar chart of tactic success by repository category'
    )
    parser.add_argument('result_json', help='Path to result.json file')
    parser.add_argument('--categories', required=True, help='Path to repo_categories.json')
    parser.add_argument('--output', default='tactic_by_category.png', help='Output chart path')

    args = parser.parse_args()

    results = load_results(args.result_json)
    categories = load_categories(args.categories)
    stats = aggregate_by_category_and_strategy(results, categories)

    print_summary(stats)
    generate_chart(stats, args.output)

    print("✓ Done!")


if __name__ == '__main__':
    main()
