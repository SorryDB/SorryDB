#!/usr/bin/env python3
"""
Analysis script for proof verification experiment results.

This script analyzes the results from proof verification experiments,
grouping results by repository and calculating verification success rates.

Can process either a single experiment directory or discover and process all
experiment subdirectories within a parent directory. Analysis files are
co-located with result.json files.
"""

import json
import argparse
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any, Tuple


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


def discover_experiments(parent_dir: Path) -> List[Path]:
    """
    Discover all subdirectories containing result.json files.

    Args:
        parent_dir: Parent directory to search for experiments

    Returns:
        Sorted list of paths to experiment directories containing result.json
    """
    if not parent_dir.exists():
        print(f"Error: Directory not found: {parent_dir}")
        return []

    if not parent_dir.is_dir():
        print(f"Error: Not a directory: {parent_dir}")
        return []

    # Find all subdirectories containing result.json
    experiment_dirs = []
    for item in parent_dir.iterdir():
        if item.is_dir():
            result_file = item / "result.json"
            if result_file.exists():
                experiment_dirs.append(item)

    return sorted(experiment_dirs)


def should_process_experiment(experiment_dir: Path, force: bool) -> Tuple[bool, str]:
    """
    Determine if an experiment should be processed.

    Args:
        experiment_dir: Path to experiment directory
        force: Whether to force reprocessing

    Returns:
        Tuple of (should_process, reason)
    """
    result_file = experiment_dir / "result.json"
    analysis_file = experiment_dir / "analysis.json"

    if not result_file.exists():
        return False, "result.json not found"

    if analysis_file.exists() and not force:
        return False, "analysis.json already exists (use --force to overwrite)"

    return True, "ready to process"


def process_single_experiment(experiment_dir: Path, force: bool) -> Dict[str, Any]:
    """
    Process a single experiment directory.

    Args:
        experiment_dir: Path to experiment directory
        force: Whether to force reprocessing

    Returns:
        Dictionary with processing status and details
    """
    experiment_name = experiment_dir.name
    result = {
        'experiment_name': experiment_name,
        'experiment_dir': str(experiment_dir),
        'status': 'unknown',
        'message': ''
    }

    # Check if should process
    should_process, reason = should_process_experiment(experiment_dir, force)
    if not should_process:
        result['status'] = 'skipped'
        result['message'] = reason
        return result

    try:
        # Load results
        result_file = experiment_dir / "result.json"
        data = load_results(str(result_file))

        # Analyze
        repo_stats = analyze_by_repo(data)
        summary = calculate_summary(repo_stats)

        # Write outputs to same directory as result.json
        output_json = experiment_dir / "analysis.json"
        output_md = experiment_dir / "analysis.md"

        write_json_output(repo_stats, summary, str(output_json))
        write_markdown_output(repo_stats, summary, str(output_md))

        result['status'] = 'success'
        result['message'] = f"Analyzed {summary['total_sorries']} sorries, {summary['total_verified']} verified"
        result['summary'] = summary

    except Exception as e:
        result['status'] = 'error'
        result['message'] = f"Error: {type(e).__name__}: {str(e)}"

    return result


def print_processing_summary(results: List[Dict[str, Any]]):
    """Print a summary of processing results."""
    print("\n" + "="*80)
    print("PROCESSING SUMMARY")
    print("="*80)

    success_count = sum(1 for r in results if r['status'] == 'success')
    skipped_count = sum(1 for r in results if r['status'] == 'skipped')
    error_count = sum(1 for r in results if r['status'] == 'error')

    print(f"Total experiments found: {len(results)}")
    print(f"  Successfully analyzed: {success_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Errors: {error_count}")
    print("")

    # Show details for each experiment
    for result in results:
        status_symbol = "✓" if result['status'] == 'success' else "⊘" if result['status'] == 'skipped' else "✗"
        print(f"{status_symbol} {result['experiment_name']}: {result['message']}")

    print("="*80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze proof verification experiment results by repository. '
                    'Discovers all experiment subdirectories with result.json and generates '
                    'analysis.json/analysis.md files co-located with the results.'
    )
    parser.add_argument(
        'parent_dir',
        help='Parent directory containing experiment subdirectories '
             '(e.g., intermediate_experiment_outputs/simple)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force reprocessing even if analysis.json already exists'
    )

    args = parser.parse_args()

    # Convert to Path
    parent_dir = Path(args.parent_dir)

    # Discover experiments
    print(f"Discovering experiments in {parent_dir}...")
    experiment_dirs = discover_experiments(parent_dir)

    if not experiment_dirs:
        print(f"No experiment directories found in {parent_dir}")
        print("(Looking for subdirectories containing result.json)")
        return

    print(f"Found {len(experiment_dirs)} experiment(s)")
    print("")

    # Process each experiment
    results = []
    for i, experiment_dir in enumerate(experiment_dirs, 1):
        print(f"[{i}/{len(experiment_dirs)}] Processing {experiment_dir.name}...")
        result = process_single_experiment(experiment_dir, args.force)
        results.append(result)
        print("")

    # Print summary
    print_processing_summary(results)

    print("✓ Analysis complete!")


if __name__ == '__main__':
    main()
