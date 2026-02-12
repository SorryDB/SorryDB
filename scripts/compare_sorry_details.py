#!/usr/bin/env python3
"""
Sorry-level strategy comparison script.

Compares two strategies at the individual sorry level, showing which sorries
each strategy solved, with example proofs and attempt counts.

Usage:
    python scripts/compare_sorry_details.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --strategies claude goedel \
        --subfolder 1000 \
        --output comparison_details.md \
        --filter-repo owner/repo  # optional
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


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
        print(f"  Note: Multiple experiments found, using most recent: {experiment_dirs[-1].name}")
        return experiment_dirs[-1]

    return experiment_dirs[0]


def load_result_data(result_json_path: Path) -> List[Dict[str, Any]]:
    """Load and parse result.json file."""
    with open(result_json_path, 'r') as f:
        return json.load(f)


def extract_repo_name(repo_url: str) -> str:
    """Extract owner/repo from GitHub URL."""
    url = repo_url.rstrip('/').removesuffix('.git')
    if url.startswith('https://github.com/'):
        return url.replace('https://github.com/', '')
    return url


def build_sorry_lookup(
    data: List[Dict[str, Any]],
    filter_repo: Optional[str] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Build a lookup dictionary from sorry_id to sorry data.

    Args:
        data: List of result entries from result.json
        filter_repo: Optional repo filter (e.g., 'owner/repo')

    Returns:
        Dict mapping sorry_id to parsed sorry data
    """
    lookup = {}

    for entry in data:
        sorry = entry.get('sorry', {})
        sorry_id = sorry.get('id')
        if not sorry_id:
            continue

        repo_url = sorry.get('repo', {}).get('remote', '')
        repo_name = extract_repo_name(repo_url)

        # Apply repo filter if specified
        if filter_repo and filter_repo.lower() not in repo_name.lower():
            continue

        location = sorry.get('location', {})
        debug_info = sorry.get('debug_info', {})

        # Get proof attempts count
        proof_attempts = entry.get('proof_attempts') or []
        attempt_count = len(proof_attempts) if proof_attempts else 0

        lookup[sorry_id] = {
            'id': sorry_id,
            'repo': repo_name,
            'file': location.get('path', ''),
            'line': location.get('start_line', 0),
            'goal': debug_info.get('goal', ''),
            'url': debug_info.get('url', ''),
            'proof': entry.get('proof'),
            'proof_verified': entry.get('proof_verified', False),
            'proof_attempts': proof_attempts,
            'attempt_count': attempt_count,
            'strategy_name': entry.get('strategy_name', '')
        }

    return lookup


def compare_strategies(
    lookup_a: Dict[str, Dict[str, Any]],
    lookup_b: Dict[str, Dict[str, Any]],
    strategy_a: str,
    strategy_b: str
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Compare two strategy lookups and categorize sorries.

    Returns dict with keys:
        - 'a_only': solved by A only
        - 'b_only': solved by B only
        - 'both': solved by both
        - 'neither': solved by neither
    """
    all_sorry_ids = set(lookup_a.keys()) | set(lookup_b.keys())

    a_only = []
    b_only = []
    both = []
    neither = []

    for sorry_id in all_sorry_ids:
        entry_a = lookup_a.get(sorry_id)
        entry_b = lookup_b.get(sorry_id)

        verified_a = entry_a['proof_verified'] if entry_a else False
        verified_b = entry_b['proof_verified'] if entry_b else False

        # Use whichever entry has data for base info
        base_entry = entry_a or entry_b

        # Get failed proof attempts (first one as example)
        a_failed_example = None
        b_failed_example = None
        if entry_a and not verified_a and entry_a['proof_attempts']:
            a_failed_example = entry_a['proof_attempts'][0]
        if entry_b and not verified_b and entry_b['proof_attempts']:
            b_failed_example = entry_b['proof_attempts'][0]

        result = {
            'id': sorry_id,
            'repo': base_entry['repo'],
            'file': base_entry['file'],
            'line': base_entry['line'],
            'goal': base_entry['goal'],
            'url': base_entry['url'],
            f'{strategy_a}_verified': verified_a,
            f'{strategy_b}_verified': verified_b,
            f'{strategy_a}_proof': entry_a['proof'] if entry_a and verified_a else None,
            f'{strategy_b}_proof': entry_b['proof'] if entry_b and verified_b else None,
            f'{strategy_a}_attempts': entry_a['attempt_count'] if entry_a else 0,
            f'{strategy_b}_attempts': entry_b['attempt_count'] if entry_b else 0,
            f'{strategy_a}_failed_example': a_failed_example,
            f'{strategy_b}_failed_example': b_failed_example,
        }

        if verified_a and verified_b:
            both.append(result)
        elif verified_a and not verified_b:
            a_only.append(result)
        elif not verified_a and verified_b:
            b_only.append(result)
        else:
            neither.append(result)

    # Sort all lists by repo, file, line
    def sort_key(x):
        return (x['repo'], x['file'], x['line'])

    return {
        'a_only': sorted(a_only, key=sort_key),
        'b_only': sorted(b_only, key=sort_key),
        'both': sorted(both, key=sort_key),
        'neither': sorted(neither, key=sort_key)
    }


def truncate(text: str, max_len: int) -> str:
    """Truncate text and add ellipsis if needed."""
    if not text:
        return ''
    # Replace newlines with spaces for table display
    text = text.replace('\n', ' ').replace('\r', '')
    if len(text) > max_len:
        return text[:max_len - 3] + '...'
    return text


def escape_markdown(text: str) -> str:
    """Escape markdown special characters in table cells."""
    if not text:
        return ''
    # Escape pipe characters which break tables
    return text.replace('|', '\\|')


def generate_markdown(
    comparison: Dict[str, List[Dict[str, Any]]],
    strategy_a: str,
    strategy_b: str,
    lookup_a: Dict[str, Dict[str, Any]],
    lookup_b: Dict[str, Dict[str, Any]],
    output_path: str
):
    """Generate markdown comparison report."""
    lines = []

    # Title
    lines.append(f"# Sorry-Level Comparison: {strategy_a} vs {strategy_b}")
    lines.append("")

    # Summary
    total_a = len(lookup_a)
    total_b = len(lookup_b)
    verified_a = sum(1 for e in lookup_a.values() if e['proof_verified'])
    verified_b = sum(1 for e in lookup_b.values() if e['proof_verified'])
    rate_a = (verified_a / total_a * 100) if total_a > 0 else 0
    rate_b = (verified_b / total_b * 100) if total_b > 0 else 0

    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | {strategy_a} | {strategy_b} |")
    lines.append("|--------|------------|------------|")
    lines.append(f"| Total Sorries | {total_a} | {total_b} |")
    lines.append(f"| Verified | {verified_a} | {verified_b} |")
    lines.append(f"| Success Rate | {rate_a:.1f}% | {rate_b:.1f}% |")
    lines.append("")

    # Breakdown
    lines.append("## Breakdown")
    lines.append("")
    lines.append(f"- Solved by **{strategy_a} only**: {len(comparison['a_only'])}")
    lines.append(f"- Solved by **{strategy_b} only**: {len(comparison['b_only'])}")
    lines.append(f"- Solved by **both**: {len(comparison['both'])}")
    lines.append(f"- Solved by **neither**: {len(comparison['neither'])}")
    lines.append("")

    # Solved by A only
    lines.append(f"## Solved by {strategy_a} only ({len(comparison['a_only'])} sorries)")
    lines.append("")
    if comparison['a_only']:
        lines.append(f"| Repository | File:Line | Goal | {strategy_a} Proof | {strategy_b} attempts | {strategy_b} failed example |")
        lines.append("|------------|-----------|------|------------|---------------------|--------------------------|")
        for entry in comparison['a_only']:
            repo = entry['repo']
            file_line = f"{entry['file']}:{entry['line']}"
            goal = escape_markdown(truncate(entry['goal'], 40))
            proof = escape_markdown(truncate(entry[f'{strategy_a}_proof'] or '', 60))
            attempts = entry[f'{strategy_b}_attempts']
            failed_example = escape_markdown(truncate(entry[f'{strategy_b}_failed_example'] or '(none)', 60))
            lines.append(f"| {repo} | {file_line} | `{goal}` | `{proof}` | {attempts} | `{failed_example}` |")
    else:
        lines.append("(none)")
    lines.append("")

    # Solved by B only
    lines.append(f"## Solved by {strategy_b} only ({len(comparison['b_only'])} sorries)")
    lines.append("")
    if comparison['b_only']:
        lines.append(f"| Repository | File:Line | Goal | {strategy_b} Proof | {strategy_a} attempts | {strategy_a} failed example |")
        lines.append("|------------|-----------|------|------------|---------------------|--------------------------|")
        for entry in comparison['b_only']:
            repo = entry['repo']
            file_line = f"{entry['file']}:{entry['line']}"
            goal = escape_markdown(truncate(entry['goal'], 40))
            proof = escape_markdown(truncate(entry[f'{strategy_b}_proof'] or '', 60))
            attempts = entry[f'{strategy_a}_attempts']
            failed_example = escape_markdown(truncate(entry[f'{strategy_a}_failed_example'] or '(none)', 60))
            lines.append(f"| {repo} | {file_line} | `{goal}` | `{proof}` | {attempts} | `{failed_example}` |")
    else:
        lines.append("(none)")
    lines.append("")

    # Solved by both
    lines.append(f"## Solved by both ({len(comparison['both'])} sorries)")
    lines.append("")
    if comparison['both']:
        lines.append(f"| Repository | File:Line | {strategy_a} proof | {strategy_b} proof |")
        lines.append("|------------|-----------|-------------------|-------------------|")
        for entry in comparison['both']:
            repo = entry['repo']
            file_line = f"{entry['file']}:{entry['line']}"
            proof_a = escape_markdown(truncate(entry[f'{strategy_a}_proof'] or '', 60))
            proof_b = escape_markdown(truncate(entry[f'{strategy_b}_proof'] or '', 60))
            lines.append(f"| {repo} | {file_line} | `{proof_a}` | `{proof_b}` |")
    else:
        lines.append("(none)")
    lines.append("")

    # Solved by neither (count only)
    lines.append(f"## Solved by neither ({len(comparison['neither'])} sorries)")
    lines.append("")
    lines.append(f"*{len(comparison['neither'])} sorries were not solved by either strategy.*")
    lines.append("")

    # Write to file
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    print(f"✓ Comparison written to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Compare two strategies at the sorry level, outputting a detailed markdown report.'
    )
    parser.add_argument(
        '--base-dir',
        required=True,
        help='Base directory containing strategy folders'
    )
    parser.add_argument(
        '--strategies',
        nargs=2,
        required=True,
        metavar=('STRATEGY_A', 'STRATEGY_B'),
        help='Exactly 2 strategies to compare'
    )
    parser.add_argument(
        '--subfolder',
        required=True,
        help='Subfolder within each strategy (e.g., "1000")'
    )
    parser.add_argument(
        '--output',
        default='comparison_details.md',
        help='Output markdown file path (default: comparison_details.md)'
    )
    parser.add_argument(
        '--filter-repo',
        help='Filter to specific repo (e.g., "owner/repo"). Case-insensitive partial match.'
    )

    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        print(f"Error: Base directory does not exist: {base_dir}")
        sys.exit(1)

    strategy_a, strategy_b = args.strategies

    # Discover experiment directories
    print(f"Discovering experiments in {base_dir}...")
    exp_dir_a = discover_experiment_for_strategy(base_dir, strategy_a, args.subfolder)
    exp_dir_b = discover_experiment_for_strategy(base_dir, strategy_b, args.subfolder)

    print(f"  {strategy_a}: {exp_dir_a.name}")
    print(f"  {strategy_b}: {exp_dir_b.name}")

    # Load result data
    print("\nLoading result data...")
    data_a = load_result_data(exp_dir_a / "result.json")
    data_b = load_result_data(exp_dir_b / "result.json")

    # Build sorry lookups
    print("Building sorry lookups...")
    lookup_a = build_sorry_lookup(data_a, args.filter_repo)
    lookup_b = build_sorry_lookup(data_b, args.filter_repo)

    if args.filter_repo:
        print(f"  Filtered to repo: {args.filter_repo}")
        print(f"  {strategy_a}: {len(lookup_a)} sorries")
        print(f"  {strategy_b}: {len(lookup_b)} sorries")
    else:
        print(f"  {strategy_a}: {len(lookup_a)} sorries")
        print(f"  {strategy_b}: {len(lookup_b)} sorries")

    # Compare strategies
    print("\nComparing strategies...")
    comparison = compare_strategies(lookup_a, lookup_b, strategy_a, strategy_b)

    print(f"  Solved by {strategy_a} only: {len(comparison['a_only'])}")
    print(f"  Solved by {strategy_b} only: {len(comparison['b_only'])}")
    print(f"  Solved by both: {len(comparison['both'])}")
    print(f"  Solved by neither: {len(comparison['neither'])}")

    # Generate markdown
    print("\nGenerating markdown...")
    generate_markdown(comparison, strategy_a, strategy_b, lookup_a, lookup_b, args.output)

    print("\n✓ Done!")


if __name__ == '__main__':
    main()
