#!/usr/bin/env python3
"""
Generate RatingExperiments input JSON from SorryDB experiment results.

Converts experiment result.json files into the flat attempts list format
expected by RatingExperiments rate.py.

Usage:
    python scripts/generate_rating_attempts.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --strategies claude gemini gemini-pro gpt agentic gemini_agentic goedel multi_tactic qwen rfl \
        --subfolder 1000 \
        --output rating_attempts.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


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


def load_merged_results(experiment_dir: Path) -> List[Dict[str, Any]]:
    """
    Load result.json, merging with all reruns in timestamp order.
    Later reruns take precedence by sorry ID.

    Merge order: main -> oldest rerun -> ... -> most recent rerun

    Args:
        experiment_dir: Path to experiment directory containing result.json

    Returns:
        List of merged result entries
    """
    # Load main results
    main_result = experiment_dir / "result.json"
    with open(main_result, 'r') as f:
        main_data = json.load(f)

    # Start with main results indexed by sorry ID
    merged_by_id = {entry['sorry']['id']: entry for entry in main_data}

    # Check for reruns
    rerun_dir = experiment_dir / "rerun"
    if rerun_dir.exists():
        # Find all rerun subdirs with result.json
        rerun_subdirs = [
            d for d in rerun_dir.iterdir()
            if d.is_dir() and (d / "result.json").exists()
        ]

        if rerun_subdirs:
            # Sort by timestamp (oldest first, most recent last)
            rerun_subdirs = sorted(rerun_subdirs, key=lambda d: d.name)

            # Merge each rerun in order (later overwrites earlier)
            for rerun_subdir in rerun_subdirs:
                rerun_result = rerun_subdir / "result.json"
                with open(rerun_result, 'r') as f:
                    rerun_data = json.load(f)
                for entry in rerun_data:
                    sorry_id = entry['sorry']['id']
                    merged_by_id[sorry_id] = entry  # overwrite with rerun

    return list(merged_by_id.values())


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
                # Distinguish tools vs no-tools agentic
                enable_tools = run_summary['strategy']['args'].get('enable_tools', False)
                suffix = "agentic w/ tools" if enable_tools else "agentic"
                return f"{model} ({suffix})"
            except KeyError:
                pass  # Fall through to return just "agentic"

        # For non-LLM strategies, return strategy name
        return strategy_name

    except (KeyError, json.JSONDecodeError):
        return experiment_dir.name


def generate_attempts(
    base_dir: Path,
    strategies: List[str],
    subfolder: str,
) -> List[Dict[str, str]]:
    """
    Generate the attempts list for all strategies.

    Returns:
        List of {"agent": str, "problem": str, "outcome": str} dicts
    """
    attempts = []

    for strategy in strategies:
        experiment_dir = discover_experiment_for_strategy(base_dir, strategy, subfolder)
        agent_name = derive_experiment_name(experiment_dir)

        results = load_merged_results(experiment_dir)

        solved = sum(1 for e in results if e.get('proof_verified', False))
        print(f"  {agent_name}: {len(results)} results, {solved} solved (from {experiment_dir.name})")

        for entry in results:
            sorry_id = entry.get('sorry', {}).get('id')
            if sorry_id is None:
                continue

            proof_verified = entry.get('proof_verified', False)
            outcome = "solved" if proof_verified else "failed"

            attempts.append({
                "agent": agent_name,
                "problem": sorry_id,
                "outcome": outcome,
            })

    return attempts


def main():
    parser = argparse.ArgumentParser(
        description='Generate RatingExperiments input JSON from SorryDB experiment results'
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
        help='List of strategy names to include'
    )
    parser.add_argument(
        '--subfolder',
        required=True,
        help='Subfolder within each strategy (e.g., "1000")'
    )
    parser.add_argument(
        '--output',
        required=True,
        help='Output path for the attempts JSON file'
    )

    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        print(f"Error: Base directory does not exist: {base_dir}")
        sys.exit(1)

    print(f"Loading experiments from {base_dir}...")
    attempts = generate_attempts(base_dir, args.strategies, args.subfolder)

    # Summary statistics
    agents = set(a["agent"] for a in attempts)
    problems = set(a["problem"] for a in attempts)
    solved = sum(1 for a in attempts if a["outcome"] == "solved")
    print(f"\nGenerated {len(attempts)} attempts:")
    print(f"  {len(agents)} agents, {len(problems)} problems")
    print(f"  {solved} solved, {len(attempts) - solved} failed")

    # Check for duplicate display names
    if len(agents) < len(args.strategies):
        print(f"\n  Warning: {len(args.strategies)} strategies mapped to only {len(agents)} unique agent names.")
        print("  Some strategies may share a display name. Check run_summary.json metadata.")

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(attempts, f, indent=2)

    print(f"\nAttempts written to {args.output}")


if __name__ == '__main__':
    main()
