#!/usr/bin/env python3
"""
Extract proof lengths across strategies for comparison.

Discovers experiments by strategy name and subfolder, extracts proof lengths
from successful_attempts, and outputs a JSON mapping from (sorry_id, strategy)
to average proof length.

Usage:
    python scripts/extract_proof_lengths.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --strategies claude gemini agentic goedel \
        --subfolder 1000 \
        --output proof_lengths.json
"""

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Set


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


def extract_proof_lengths_from_result(result_json_path: Path) -> Dict[str, Dict[str, Any]]:
    """
    Extract proof lengths from a result.json file.

    Args:
        result_json_path: Path to result.json file

    Returns:
        Dict mapping sorry_id -> {avg_length, num_proofs, lengths}
    """
    with open(result_json_path, 'r') as f:
        data = json.load(f)

    results: Dict[str, Dict[str, Any]] = {}

    for entry in data:
        if not entry.get('proof_verified', False):
            continue

        sorry_id = entry.get('sorry', {}).get('id')
        if not sorry_id:
            continue

        successful_attempts = entry.get('successful_attempts') or []
        if not successful_attempts:
            continue

        # Calculate lengths (character count)
        lengths = [len(proof) for proof in successful_attempts]

        results[sorry_id] = {
            'avg_length': statistics.mean(lengths),
            'num_proofs': len(lengths),
            'lengths': lengths
        }

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Extract proof lengths across strategies for comparison'
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
        help='List of strategy names to compare'
    )
    parser.add_argument(
        '--subfolder',
        required=True,
        help='Subfolder within each strategy (e.g., "1000")'
    )
    parser.add_argument(
        '--output',
        default='proof_lengths.json',
        help='Output JSON file path (default: proof_lengths.json)'
    )

    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        print(f"Error: Base directory does not exist: {base_dir}")
        sys.exit(1)

    # Discover experiment directories for each strategy
    print(f"Discovering experiments in {base_dir}...")
    experiment_dirs: Dict[str, Path] = {}

    for strategy in args.strategies:
        experiment_dir = discover_experiment_for_strategy(base_dir, strategy, args.subfolder)
        print(f"  {strategy}: {experiment_dir.name}")
        experiment_dirs[strategy] = experiment_dir

    print()

    # Extract proof lengths for each strategy
    print("Extracting proof lengths...")
    by_sorry_strategy: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for strategy, exp_dir in experiment_dirs.items():
        result_json = exp_dir / "result.json"
        proof_lengths = extract_proof_lengths_from_result(result_json)
        print(f"  {strategy}: {len(proof_lengths)} verified sorries with proofs")

        for sorry_id, length_data in proof_lengths.items():
            if sorry_id not in by_sorry_strategy:
                by_sorry_strategy[sorry_id] = {}
            by_sorry_strategy[sorry_id][strategy] = length_data

    print()

    # Find sorries solved by multiple strategies
    sorries_solved_by_multiple: List[str] = [
        sorry_id for sorry_id, strategies in by_sorry_strategy.items()
        if len(strategies) >= 2
    ]
    sorries_solved_by_multiple.sort()

    print(f"Total sorries with verified proofs: {len(by_sorry_strategy)}")
    print(f"Sorries solved by 2+ strategies: {len(sorries_solved_by_multiple)}")

    # Build output
    output = {
        'by_sorry_strategy': by_sorry_strategy,
        'sorries_solved_by_multiple': sorries_solved_by_multiple,
        'metadata': {
            'strategies': args.strategies,
            'subfolder': args.subfolder,
            'length_metric': 'characters',
            'base_dir': str(base_dir)
        }
    }

    # Write output
    output_path = Path(args.output)
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\nOutput written to: {output_path}")


if __name__ == '__main__':
    main()
