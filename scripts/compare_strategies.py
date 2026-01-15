#!/usr/bin/env python3
"""
Strategy-based experiment comparison script.

Discovers experiments by strategy name and subfolder, then calls compare_experiments.py
to generate the comparison.

Usage:
    python scripts/compare_strategies.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --strategies claude gemini gpt multi_tactic \
        --subfolder 1000
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set


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

    # Find all subdirectories containing analysis.json
    experiment_dirs = [
        d for d in strategy_path.iterdir()
        if d.is_dir() and (d / "analysis.json").exists()
    ]

    if len(experiment_dirs) == 0:
        print(f"Error: No experiments found in {strategy_path}")
        print("(Looking for subdirectories containing analysis.json)")
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


def compute_combined_by_category(
    experiment_dirs: List[Path],
    categories_path: Path
) -> Dict[str, int]:
    """
    Compute combined (union) totals per category across all strategies.

    Args:
        experiment_dirs: List of experiment directory paths
        categories_path: Path to repo_categories.json file

    Returns:
        Dict mapping category -> count of unique sorries solved
    """
    # Load categories mapping
    categories = load_categories(categories_path)

    # Collect all verified sorries with their repos across all strategies
    # sorry_id -> repo_url (any strategy that solved it)
    all_verified: Dict[str, str] = {}

    for exp_dir in experiment_dirs:
        result_json = exp_dir / "result.json"
        if result_json.exists():
            verified = load_verified_sorries_with_repo(result_json)
            # Merge - if same sorry solved by multiple strategies, repo should be same
            all_verified.update(verified)

    # Count per category
    category_counts: Dict[str, int] = {}
    for sorry_id, repo_url in all_verified.items():
        repo_name = extract_repo_name(repo_url)
        category = categories.get(repo_name, 'unknown')
        category_counts[category] = category_counts.get(category, 0) + 1

    return category_counts


def compute_combined_total(experiment_dirs: List[Path], strategies: List[str]) -> int:
    """
    Compute total unique sorries solved across all strategies (union).

    Args:
        experiment_dirs: List of experiment directory paths
        strategies: List of strategy names (same order as experiment_dirs)

    Returns:
        Number of unique sorries solved by at least one strategy
    """
    all_solved: Set[str] = set()

    for strategy, exp_dir in zip(strategies, experiment_dirs):
        result_json = exp_dir / "result.json"
        if result_json.exists():
            verified_ids = load_verified_sorry_ids(result_json)
            all_solved.update(verified_ids)

    return len(all_solved)


def main():
    parser = argparse.ArgumentParser(
        description='Discover experiments by strategy and subfolder, then run compare_experiments.py'
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
        '--plot-combined',
        action='store_true',
        help='Add a "Combined" bar to the totals chart showing total unique sorries solved across all strategies'
    )

    # Parse known args, pass the rest through to compare_experiments.py
    args, passthrough_args = parser.parse_known_args()

    # Validate minimum strategies
    if len(args.strategies) < 2:
        print(f"Error: Need at least 2 strategies to compare, got {len(args.strategies)}")
        sys.exit(1)

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        print(f"Error: Base directory does not exist: {base_dir}")
        sys.exit(1)

    # Discover experiment directories for each strategy
    print(f"Discovering experiments in {base_dir}...")
    experiment_dirs: List[Path] = []

    for strategy in args.strategies:
        experiment_dir = discover_experiment_for_strategy(base_dir, strategy, args.subfolder)
        print(f"  {strategy}: {experiment_dir.name}")
        experiment_dirs.append(experiment_dir)

    print()

    # Build compare_experiments.py command
    compare_script = Path(__file__).parent.parent / "intermediate_experiment_outputs" / "compare_experiments.py"

    cmd = [sys.executable, str(compare_script)]
    cmd.extend(str(d) for d in experiment_dirs)

    # Compute and pass combined totals if requested
    if args.plot_combined:
        combined_total = compute_combined_total(experiment_dirs, args.strategies)
        print(f"Combined (union) total: {combined_total} unique sorries solved")
        cmd.extend(['--combined-total', str(combined_total)])

        # Check if --categories is in passthrough args to compute per-category combined
        categories_path = None
        for i, arg in enumerate(passthrough_args):
            if arg == '--categories' and i + 1 < len(passthrough_args):
                categories_path = Path(passthrough_args[i + 1])
                break

        if categories_path and categories_path.exists():
            combined_by_category = compute_combined_by_category(experiment_dirs, categories_path)
            print(f"Combined by category: {combined_by_category}")
            cmd.extend(['--combined-by-category', json.dumps(combined_by_category)])

    cmd.extend(passthrough_args)

    print(f"Running: {' '.join(cmd)}")
    print()

    # Execute compare_experiments.py
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == '__main__':
    main()
