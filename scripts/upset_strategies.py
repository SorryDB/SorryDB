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
from typing import Dict, Optional, Set

import matplotlib.pyplot as plt
import matplotlib
from matplotlib import cm
matplotlib.use('Agg')

import pandas as pd
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
        # Sort by directory name (timestamp format YYYY-MM-DD_HH-MM-SS_*) and pick most recent
        experiment_dirs = sorted(experiment_dirs, key=lambda d: d.name)
        print(f"  Note: Multiple experiments found, using most recent: {experiment_dirs[-1].name}")
        return experiment_dirs[-1]

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


def load_verified_sorries_with_repo(result_json_path: Path) -> Dict[str, str]:
    """
    Load result.json and return dict mapping sorry ID to repo URL for verified sorries.

    Args:
        result_json_path: Path to result.json file

    Returns:
        Dict mapping sorry_id -> repo_url for verified sorries
    """
    with open(result_json_path, 'r') as f:
        data = json.load(f)

    verified = {}
    for entry in data:
        if entry.get('proof_verified', False):
            sorry_id = entry.get('sorry', {}).get('id')
            repo_url = entry.get('sorry', {}).get('repo', {}).get('remote', '')
            if sorry_id:
                verified[sorry_id] = repo_url

    return verified


def load_categories(categories_path: Path) -> Dict[str, str]:
    """
    Load repo_categories.json and return mapping of repo name -> category.

    Args:
        categories_path: Path to repo_categories.json file

    Returns:
        Dict mapping repo_name (owner/repo) -> category
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


def derive_experiment_name(experiment_dir: Path) -> str:
    """
    Derive experiment display name from run_summary.json metadata.

    For LLM strategies: Returns model name
    For agentic strategies: Returns "{model} (agentic)"
    For other strategies: Returns strategy name

    Args:
        experiment_dir: Path to experiment directory containing run_summary.json

    Returns:
        Experiment display name
    """
    run_summary_path = experiment_dir / "run_summary.json"
    if not run_summary_path.exists():
        return experiment_dir.name

    try:
        with open(run_summary_path, 'r') as f:
            run_summary = json.load(f)

        strategy_name = run_summary['strategy']['name']

        # For LLM strategies, use the model name or provider name
        if strategy_name == 'llm':
            try:
                model = run_summary['strategy']['args']['model_config']['params']['model']
                return model
            except KeyError:
                try:
                    provider = run_summary['strategy']['args']['model_config']['provider']
                    return provider
                except KeyError:
                    return experiment_dir.parent.name

        # For agentic strategies, append the model name to disambiguate
        if strategy_name == 'agentic':
            try:
                model = run_summary['strategy']['args']['model']
                # Clean up model name (e.g., "google_genai:gemini-3-flash-preview" -> "gemini-3-flash-preview")
                if ':' in model:
                    model = model.split(':')[-1]
                return f"{model} (agentic)"
            except KeyError:
                pass  # Fall through to return just "agentic"

        # For non-LLM strategies, return strategy name
        return strategy_name

    except (KeyError, json.JSONDecodeError):
        return experiment_dir.name


def generate_upset_plot(
    strategy_sets: Dict[str, Set[str]],
    output_path: str,
    sorry_categories: Optional[Dict[str, str]] = None
):
    """
    Generate an UpSet plot showing intersections between strategy sets.

    Args:
        strategy_sets: Dict mapping strategy name to set of verified sorry IDs
        output_path: Path to save the plot
        sorry_categories: Optional dict mapping sorry_id -> category for stacked bars
    """
    # Get all unique sorry IDs
    all_sorry_ids = set()
    for ids in strategy_sets.values():
        all_sorry_ids.update(ids)

    strategy_names = list(strategy_sets.keys())

    if sorry_categories is not None:
        # Build DataFrame for stacked bars mode
        rows = []
        for sorry_id in all_sorry_ids:
            row = {
                'sorry_id': sorry_id,
                'category': sorry_categories.get(sorry_id, 'unknown')
            }
            # Add boolean column for each strategy
            for strategy in strategy_names:
                row[strategy] = sorry_id in strategy_sets[strategy]
            rows.append(row)

        df = pd.DataFrame(rows)

        # Set MultiIndex based on strategy membership
        df = df.set_index(strategy_names)

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
            title='Count by category',
            elements=10
        )

        upset.plot(fig=fig)

        # Add title
        plt.suptitle('Strategy Comparison by Category', fontsize=14, fontweight='bold')

    else:
        # Original mode without categories
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
    parser.add_argument(
        '--categories',
        help='Path to repo_categories.json for category-colored stacked bars'
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

    # Load categories if provided
    categories_map: Optional[Dict[str, str]] = None
    if args.categories:
        categories_path = Path(args.categories)
        if not categories_path.exists():
            print(f"Error: Categories file does not exist: {categories_path}")
            sys.exit(1)
        categories_map = load_categories(categories_path)
        print(f"Loaded {len(categories_map)} repo categories")

    # Discover experiment directories and derive display names
    print(f"Loading experiments from {base_dir}...")
    experiment_dirs: Dict[str, Path] = {}
    display_names: Dict[str, str] = {}
    for strategy in args.strategies:
        experiment_dir = discover_experiment_for_strategy(base_dir, strategy, args.subfolder)
        experiment_dirs[strategy] = experiment_dir
        display_names[strategy] = derive_experiment_name(experiment_dir)

    # Load verified sorry IDs for each strategy
    strategy_sets: Dict[str, Set[str]] = {}
    sorry_categories: Optional[Dict[str, str]] = None

    if categories_map is not None:
        # Load with repo info to determine categories
        sorry_categories = {}
        for strategy in args.strategies:
            result_json = experiment_dirs[strategy] / "result.json"
            verified_with_repo = load_verified_sorries_with_repo(result_json)

            # Add to strategy sets using display name
            display_name = display_names[strategy]
            strategy_sets[display_name] = set(verified_with_repo.keys())

            # Map sorry IDs to categories
            for sorry_id, repo_url in verified_with_repo.items():
                if sorry_id not in sorry_categories:
                    repo_name = extract_repo_name(repo_url)
                    sorry_categories[sorry_id] = categories_map.get(repo_name, 'unknown')

            print(f"  {display_name}: {len(strategy_sets[display_name])} verified sorries (from {experiment_dirs[strategy].name})")
    else:
        # Simple mode without categories
        for strategy in args.strategies:
            result_json = experiment_dirs[strategy] / "result.json"
            verified_ids = load_verified_sorry_ids(result_json)
            display_name = display_names[strategy]
            strategy_sets[display_name] = verified_ids
            print(f"  {display_name}: {len(verified_ids)} verified sorries (from {experiment_dirs[strategy].name})")

    # Print summary
    print_summary(strategy_sets)

    # Generate plot
    generate_upset_plot(strategy_sets, args.output, sorry_categories)

    print("✓ Done!")


if __name__ == '__main__':
    main()
