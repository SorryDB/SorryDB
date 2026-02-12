#!/usr/bin/env python3
"""
Generate markdown report of sorries uniquely solved by a single strategy.

Shows which sorries were solved by exactly one strategy, with full details
including repository, link to sorry, goal, and complete proof.

Usage:
    python scripts/unique_solves_report.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --strategies claude gemini agentic goedel \
        --subfolder 1000 \
        --output unique_solves.md
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


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
    main_result = experiment_dir / "result.json"
    with open(main_result, 'r') as f:
        main_data = json.load(f)

    merged_by_id = {entry['sorry']['id']: entry for entry in main_data}

    rerun_dir = experiment_dir / "rerun"
    if rerun_dir.exists():
        rerun_subdirs = [
            d for d in rerun_dir.iterdir()
            if d.is_dir() and (d / "result.json").exists()
        ]
        if rerun_subdirs:
            rerun_subdirs = sorted(rerun_subdirs, key=lambda d: d.name)
            for rerun_subdir in rerun_subdirs:
                with open(rerun_subdir / "result.json", 'r') as f:
                    rerun_data = json.load(f)
                for entry in rerun_data:
                    merged_by_id[entry['sorry']['id']] = entry

    return list(merged_by_id.values())


def discover_experiment_for_strategy(base_dir: Path, strategy: str, subfolder: str) -> Path:
    """
    Discover the experiment directory for a given strategy and subfolder.

    Args:
        base_dir: Base directory containing strategy folders
        strategy: Strategy name (e.g., 'claude', 'gemini')
        subfolder: Subfolder within strategy (e.g., '1000')

    Returns:
        Path to the experiment directory
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
        print(f"  Note: Multiple experiments found for {strategy}, using most recent: {experiment_dirs[-1].name}")
        return experiment_dirs[-1]

    return experiment_dirs[0]


def extract_repo_name(repo_url: str) -> str:
    """Extract owner/repo from GitHub URL."""
    url = repo_url.rstrip('/').removesuffix('.git')
    if url.startswith('https://github.com/'):
        return url.replace('https://github.com/', '')
    return url


def load_verified_sorries(experiment_dir: Path) -> Dict[str, Dict[str, Any]]:
    """
    Load results (merging with reruns) and return dict of verified sorries.

    Args:
        experiment_dir: Path to experiment directory containing result.json

    Returns:
        Dict mapping sorry_id to entry data for verified sorries only
    """
    data = load_merged_results(experiment_dir)

    verified = {}

    for entry in data:
        if not entry.get('proof_verified', False):
            continue

        sorry = entry.get('sorry', {})
        sorry_id = sorry.get('id')
        if not sorry_id:
            continue

        repo_url = sorry.get('repo', {}).get('remote', '')
        location = sorry.get('location', {})
        debug_info = sorry.get('debug_info', {})

        verified[sorry_id] = {
            'id': sorry_id,
            'repo_name': extract_repo_name(repo_url),
            'repo_url': repo_url,
            'file': location.get('path', ''),
            'line': location.get('start_line', 0),
            'goal': debug_info.get('goal', ''),
            'url': debug_info.get('url', ''),
            'proof': entry.get('proof', ''),
            'strategy_name': entry.get('strategy_name', ''),
        }

    return verified


def find_unique_solves(
    strategy_data: Dict[str, Dict[str, Dict[str, Any]]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Find sorries solved by exactly one strategy.

    Args:
        strategy_data: Dict mapping strategy name to {sorry_id: entry_data}

    Returns:
        Dict mapping strategy name to list of uniquely-solved sorry entries
    """
    # Collect all sorry IDs and which strategies solved them
    sorry_solvers: Dict[str, List[str]] = {}

    for strategy, sorries in strategy_data.items():
        for sorry_id in sorries.keys():
            if sorry_id not in sorry_solvers:
                sorry_solvers[sorry_id] = []
            sorry_solvers[sorry_id].append(strategy)

    # Find sorries solved by exactly one strategy
    unique_solves: Dict[str, List[Dict[str, Any]]] = {
        strategy: [] for strategy in strategy_data.keys()
    }

    for sorry_id, solvers in sorry_solvers.items():
        if len(solvers) == 1:
            strategy = solvers[0]
            entry = strategy_data[strategy][sorry_id]
            unique_solves[strategy].append(entry)

    # Sort each strategy's list by repo, file, line
    for strategy in unique_solves:
        unique_solves[strategy].sort(key=lambda x: (x['repo_name'], x['file'], x['line']))

    return unique_solves


def generate_markdown(
    unique_solves: Dict[str, List[Dict[str, Any]]],
    strategy_data: Dict[str, Dict[str, Dict[str, Any]]],
    output_path: str
):
    """
    Generate markdown report of uniquely-solved sorries.

    Args:
        unique_solves: Dict mapping strategy to list of uniquely-solved entries
        strategy_data: Full strategy data for summary stats
        output_path: Path to write markdown file
    """
    lines = []

    # Title
    lines.append("# Uniquely Solved Sorries Report")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"**Strategies compared:** {len(strategy_data)}")
    lines.append("")

    total_unique = sum(len(entries) for entries in unique_solves.values())
    lines.append(f"**Total unique solves:** {total_unique}")
    lines.append("")

    # Per-strategy summary table
    lines.append("| Strategy | Total Verified | Unique Solves |")
    lines.append("|----------|----------------|---------------|")
    for strategy in sorted(strategy_data.keys()):
        total = len(strategy_data[strategy])
        unique = len(unique_solves[strategy])
        lines.append(f"| {strategy} | {total} | {unique} |")
    lines.append("")

    # Generate sections for each strategy with unique solves
    for strategy in sorted(unique_solves.keys()):
        entries = unique_solves[strategy]
        if not entries:
            continue

        lines.append(f"## Unique to {strategy} ({len(entries)} sorries)")
        lines.append("")

        for i, entry in enumerate(entries, 1):
            repo_name = entry['repo_name']
            file_path = entry['file']
            line_num = entry['line']
            url = entry['url']
            goal = entry['goal'] or "(no goal available)"
            proof = entry['proof'] or "(no proof available)"

            # Header with link
            if url:
                lines.append(f"### {i}. [{repo_name}]({url}) - {file_path}:{line_num}")
            else:
                lines.append(f"### {i}. {repo_name} - {file_path}:{line_num}")
            lines.append("")

            # Goal
            lines.append("**Goal:**")
            lines.append("```lean")
            lines.append(goal.strip())
            lines.append("```")
            lines.append("")

            # Solution
            lines.append("**Solution:**")
            lines.append("```lean4")
            lines.append(proof.strip())
            lines.append("```")
            lines.append("")
            lines.append("---")
            lines.append("")

    # Write to file
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    print(f"Report written to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate markdown report of sorries uniquely solved by a single strategy.'
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
        help='List of strategies to compare (e.g., claude gemini agentic goedel)'
    )
    parser.add_argument(
        '--subfolder',
        required=True,
        help='Subfolder within each strategy (e.g., "1000")'
    )
    parser.add_argument(
        '--output',
        default='unique_solves.md',
        help='Output markdown file path (default: unique_solves.md)'
    )

    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        print(f"Error: Base directory does not exist: {base_dir}")
        sys.exit(1)

    if len(args.strategies) < 2:
        print("Error: Need at least 2 strategies to compare")
        sys.exit(1)

    # Load verified sorries for each strategy
    print(f"Loading results from {len(args.strategies)} strategies...")
    strategy_data: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for strategy in args.strategies:
        print(f"  Loading {strategy}...")
        exp_dir = discover_experiment_for_strategy(base_dir, strategy, args.subfolder)
        verified = load_verified_sorries(exp_dir)
        strategy_data[strategy] = verified
        print(f"    Found {len(verified)} verified sorries")

    # Find unique solves
    print("\nFinding uniquely-solved sorries...")
    unique_solves = find_unique_solves(strategy_data)

    total_unique = sum(len(entries) for entries in unique_solves.values())
    print(f"  Total unique solves: {total_unique}")
    for strategy in sorted(unique_solves.keys()):
        count = len(unique_solves[strategy])
        if count > 0:
            print(f"    {strategy}: {count}")

    # Generate markdown
    print("\nGenerating markdown report...")
    generate_markdown(unique_solves, strategy_data, args.output)

    print("\nDone!")


if __name__ == '__main__':
    main()
