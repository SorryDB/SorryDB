#!/usr/bin/env python3
"""
Analysis script for proof verification experiment results.

This script analyzes the results from a proof verification experiment,
grouping results by repository and calculating verification success rates.
"""

import json
import argparse
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any


def load_results(file_path: str) -> List[Dict[str, Any]]:
    """Load and parse the JSON results file."""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        print(f"✓ Loaded {len(data)} entries from {file_path}")
        return data
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {file_path}: {e}")
        exit(1)


def analyze_by_repo(data: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """
    Group results by repository and calculate statistics.

    Returns a dictionary with repo URLs as keys and stats as values:
    {
        'repo_url': {
            'total': int,
            'verified': int,
            'failed': int
        }
    }
    """
    repo_stats = defaultdict(lambda: {'total': 0, 'verified': 0, 'failed': 0})

    for entry in data:
        try:
            repo = entry['sorry']['repo']['remote']
            repo_stats[repo]['total'] += 1

            if entry['proof_verified']:
                repo_stats[repo]['verified'] += 1
            else:
                repo_stats[repo]['failed'] += 1
        except KeyError as e:
            print(f"Warning: Missing key {e} in entry, skipping...")
            continue

    return dict(repo_stats)


def calculate_summary(repo_stats: Dict[str, Dict[str, int]]) -> Dict[str, Any]:
    """Calculate overall summary statistics."""
    total_repos = len(repo_stats)
    total_sorries = sum(stats['total'] for stats in repo_stats.values())
    total_verified = sum(stats['verified'] for stats in repo_stats.values())
    total_failed = sum(stats['failed'] for stats in repo_stats.values())

    overall_success_rate = (total_verified / total_sorries * 100) if total_sorries > 0 else 0

    return {
        'total_repos': total_repos,
        'total_sorries': total_sorries,
        'total_verified': total_verified,
        'total_failed': total_failed,
        'overall_success_rate': round(overall_success_rate, 2)
    }


def write_json_output(repo_stats: Dict[str, Dict[str, int]], summary: Dict[str, Any], output_path: str):
    """Write analysis results to a JSON file."""
    # Prepare repo data with success rates
    repos_with_rates = []
    for repo, stats in repo_stats.items():
        success_rate = (stats['verified'] / stats['total'] * 100) if stats['total'] > 0 else 0
        repos_with_rates.append({
            'repo': repo,
            'total': stats['total'],
            'verified': stats['verified'],
            'failed': stats['failed'],
            'success_rate': round(success_rate, 2)
        })

    # Sort by success rate descending, then by total descending
    repos_with_rates.sort(key=lambda x: (-x['success_rate'], -x['total']))

    output = {
        'summary': summary,
        'by_repo': repos_with_rates
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"✓ JSON analysis written to {output_path}")


def write_markdown_output(repo_stats: Dict[str, Dict[str, int]], summary: Dict[str, Any], output_path: str):
    """Write analysis results to a Markdown file."""
    lines = []

    # Title and summary
    lines.append("# Proof Verification Analysis")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total Repositories**: {summary['total_repos']}")
    lines.append(f"- **Total Sorries**: {summary['total_sorries']}")
    lines.append(f"- **Total Verified**: {summary['total_verified']}")
    lines.append(f"- **Total Failed**: {summary['total_failed']}")
    lines.append(f"- **Overall Success Rate**: {summary['overall_success_rate']}%")
    lines.append("")

    # Prepare repo data with success rates
    repos_with_rates = []
    for repo, stats in repo_stats.items():
        success_rate = (stats['verified'] / stats['total'] * 100) if stats['total'] > 0 else 0
        repos_with_rates.append({
            'repo': repo,
            'total': stats['total'],
            'verified': stats['verified'],
            'failed': stats['failed'],
            'success_rate': success_rate
        })

    # Sort by success rate descending, then by total descending
    repos_with_rates.sort(key=lambda x: (-x['success_rate'], -x['total']))

    # Repository table
    lines.append("## Results by Repository")
    lines.append("")
    lines.append("| Repository | Total | Verified | Failed | Success Rate |")
    lines.append("|-----------|-------|----------|--------|--------------|")

    for repo_data in repos_with_rates:
        repo_name = repo_data['repo'].replace('https://github.com/', '')
        lines.append(
            f"| {repo_name} | {repo_data['total']} | "
            f"{repo_data['verified']} | {repo_data['failed']} | "
            f"{repo_data['success_rate']:.2f}% |"
        )

    lines.append("")

    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    print(f"✓ Markdown analysis written to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze proof verification experiment results by repository'
    )
    parser.add_argument(
        'input_file',
        nargs='?',
        default='intermediate_experiment_outputs/simple/2025-12-18_21-35-42_supersimple/result.json',
        help='Path to the input JSON file (default: intermediate_experiment_outputs/simple/2025-12-18_21-35-42_supersimple/result.json)'
    )
    parser.add_argument(
        '--output-json',
        default='analysis.json',
        help='Path for JSON output file (default: analysis.json)'
    )
    parser.add_argument(
        '--output-md',
        default='analysis.md',
        help='Path for Markdown output file (default: analysis.md)'
    )
    parser.add_argument(
        '--sort-by',
        choices=['success_rate', 'total', 'name'],
        default='success_rate',
        help='Sort repositories by this field (default: success_rate)'
    )

    args = parser.parse_args()

    # Load data
    print(f"Loading data from {args.input_file}...")
    data = load_results(args.input_file)

    # Analyze
    print("Analyzing results by repository...")
    repo_stats = analyze_by_repo(data)
    summary = calculate_summary(repo_stats)

    # Print summary to console
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total Repositories: {summary['total_repos']}")
    print(f"Total Sorries: {summary['total_sorries']}")
    print(f"Total Verified: {summary['total_verified']} ({summary['overall_success_rate']}%)")
    print(f"Total Failed: {summary['total_failed']}")
    print("="*60 + "\n")

    # Write outputs
    write_json_output(repo_stats, summary, args.output_json)
    write_markdown_output(repo_stats, summary, args.output_md)

    print("\n✓ Analysis complete!")


if __name__ == '__main__':
    main()
