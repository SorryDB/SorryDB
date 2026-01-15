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
import subprocess
import sys
from pathlib import Path
from typing import List


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
    cmd.extend(passthrough_args)

    print(f"Running: {' '.join(cmd)}")
    print()

    # Execute compare_experiments.py
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == '__main__':
    main()
