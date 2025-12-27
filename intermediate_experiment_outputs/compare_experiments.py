#!/usr/bin/env python3
"""
Comparison script for proof verification experiment analyses.

This script compares multiple experiment runs by loading their analysis.json and
run_summary.json files from experiment directories. Creates side-by-side comparisons
showing how each repository performed across experiments.

Usage:
    compare_experiments.py experiment_folder1/ experiment_folder2/ [experiment_folder3/ ...]
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


def load_run_summary(folder_path: str) -> Dict[str, Any]:
    """Load and parse run_summary.json from an experiment folder."""
    run_summary_path = Path(folder_path) / "run_summary.json"
    try:
        with open(run_summary_path, 'r') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"Error: run_summary.json not found in {folder_path}")
        exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {run_summary_path}: {e}")
        exit(1)


def load_analysis(folder_path: str) -> Dict[str, Any]:
    """Load and parse analysis.json from an experiment folder."""
    analysis_path = Path(folder_path) / "analysis.json"
    try:
        with open(analysis_path, 'r') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"Error: analysis.json not found in {folder_path}")
        exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {analysis_path}: {e}")
        exit(1)


def derive_experiment_name_from_summary(folder_path: str, run_summary: Dict[str, Any]) -> str:
    """
    Derive experiment name from run_summary.json metadata.

    For non-LLM strategies: Returns strategy name (e.g., 'rfl', 'supersimple')
    For LLM strategies: Returns provider name (e.g., 'gemini', 'claude', 'deepseek')

    Args:
        folder_path: Path to experiment folder
        run_summary: Parsed run_summary.json data

    Returns:
        Experiment name string
    """
    try:
        strategy_name = run_summary['strategy']['name']

        # For LLM strategies, use the provider name
        if strategy_name == 'llm':
            try:
                provider = run_summary['strategy']['args']['model_config']['provider']
                return provider
            except KeyError:
                # Fallback: extract from parent directory name
                folder_path_obj = Path(folder_path)
                parent_dir = folder_path_obj.parent.name
                print(f"Warning: Could not find provider in run_summary.json, using parent directory: {parent_dir}")
                return parent_dir

        # For non-LLM strategies, return strategy name
        return strategy_name

    except KeyError as e:
        print(f"Error: Missing key {e} in run_summary.json for {folder_path}")
        # Fallback to folder name
        return Path(folder_path).name


def load_experiment_data(folder_path: str) -> Tuple[str, Dict[str, Any]]:
    """
    Load experiment data from a folder containing analysis.json and run_summary.json.

    Args:
        folder_path: Path to experiment folder

    Returns:
        Tuple of (experiment_name, analysis_data)
    """
    folder_path_obj = Path(folder_path)

    if not folder_path_obj.exists():
        print(f"Error: Folder not found: {folder_path}")
        exit(1)

    if not folder_path_obj.is_dir():
        print(f"Error: Not a directory: {folder_path}")
        exit(1)

    # Load run summary and derive experiment name
    run_summary = load_run_summary(folder_path)
    experiment_name = derive_experiment_name_from_summary(folder_path, run_summary)

    # Load analysis data
    analysis = load_analysis(folder_path)

    print(f"✓ Loaded experiment '{experiment_name}' from {folder_path}")

    return experiment_name, analysis


def build_repo_lookup(analysis: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build a lookup dictionary from repo URL to stats."""
    return {repo['repo']: repo for repo in analysis['by_repo']}


def compare_analyses(experiments: List[Tuple[str, Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Compare N analyses and build a unified comparison structure.

    Args:
        experiments: List of (experiment_name, analysis_data) tuples

    Returns:
        Dictionary with comparison data including all repos from all analyses.
    """
    # Build repo lookups for each experiment
    repo_lookups = {name: build_repo_lookup(analysis) for name, analysis in experiments}

    # Get union of all repos across all experiments
    all_repos = set()
    for lookup in repo_lookups.values():
        all_repos.update(lookup.keys())

    # Build comparison data
    comparison = []
    empty_stats = {'total': 0, 'verified': 0, 'failed': 0, 'success_rate': 0.0}

    for repo in sorted(all_repos):
        repo_entry = {'repo': repo}

        # Add stats for each experiment
        for name, _ in experiments:
            repo_entry[name] = repo_lookups[name].get(repo, empty_stats.copy())

        # Calculate variance (max - min success rate) for sorting
        rates = [repo_entry[name]['success_rate'] for name, _ in experiments]
        variance = max(rates) - min(rates) if rates else 0
        repo_entry['_variance'] = variance

        comparison.append(repo_entry)

    # Sort by variance (biggest differences first)
    comparison.sort(key=lambda x: x['_variance'], reverse=True)

    # Remove temporary variance field
    for entry in comparison:
        del entry['_variance']

    # Build summaries dict
    summaries = {name: analysis['summary'] for name, analysis in experiments}

    # Extract experiment names
    experiment_names = [name for name, _ in experiments]

    return {
        'experiment_names': experiment_names,
        'summaries': summaries,
        'by_repo': comparison
    }


def write_json_output(comparison: Dict[str, Any], output_path: str):
    """Write comparison results to a JSON file."""
    with open(output_path, 'w') as f:
        json.dump(comparison, f, indent=2)
    print(f"✓ JSON comparison written to {output_path}")


def write_markdown_output(comparison: Dict[str, Any], output_path: str):
    """Write comparison results to a Markdown file."""
    lines = []
    experiment_names = comparison['experiment_names']
    summaries = comparison['summaries']

    # Title
    title = " vs ".join(experiment_names)
    lines.append(f"# Experiment Comparison: {title}")
    lines.append("")

    # Summary comparison
    lines.append("## Summary Comparison")
    lines.append("")

    # Build header row
    header = "| Metric | " + " | ".join(experiment_names) + " |"
    separator = "|--------|" + "|".join(["---------" for _ in experiment_names]) + "|"
    lines.append(header)
    lines.append(separator)

    # Metrics rows
    metrics = [
        ('Total Repositories', 'total_repos'),
        ('Total Sorries', 'total_sorries'),
        ('Total Verified', 'total_verified'),
        ('Total Failed', 'total_failed'),
        ('Overall Success Rate', 'overall_success_rate')
    ]

    for metric_name, metric_key in metrics:
        row = f"| {metric_name} |"
        for name in experiment_names:
            value = summaries[name][metric_key]
            if metric_key == 'overall_success_rate':
                row += f" {value}% |"
            else:
                row += f" {value} |"
        lines.append(row)

    lines.append("")

    # Repository comparison table
    lines.append("## Results by Repository")
    lines.append("")
    lines.append(f"Sorted by variance (biggest differences across experiments)")
    lines.append("")

    # Build table header
    header_parts = ["| Repository |"]
    separator_parts = ["|-----------|"]

    for name in experiment_names:
        header_parts.append(f" {name} (V/T) |")
        header_parts.append(f" {name} Rate |")
        separator_parts.append("---------------|")
        separator_parts.append("--------------|")

    lines.append("".join(header_parts))
    lines.append("".join(separator_parts))

    # Build table rows
    for entry in comparison['by_repo']:
        repo_name = entry['repo'].replace('https://github.com/', '')
        row_parts = [f"| {repo_name} |"]

        for name in experiment_names:
            stats = entry[name]
            # Format verified/total
            if stats['total'] > 0:
                v_t = f"{stats['verified']}/{stats['total']}"
                rate = f"{stats['success_rate']:.1f}%"
            else:
                v_t = "—"
                rate = "—"

            row_parts.append(f" {v_t} |")
            row_parts.append(f" {rate} |")

        lines.append("".join(row_parts))

    lines.append("")

    # Add legend
    lines.append("## Legend")
    lines.append("")
    lines.append("- **V/T**: Verified / Total sorries")
    lines.append("- **Rate**: Success rate percentage")
    lines.append("- **—**: No data for this experiment")
    lines.append("")

    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    print(f"✓ Markdown comparison written to {output_path}")


def generate_chart(comparison: Dict[str, Any], output_path: str):
    """Generate a grouped bar chart comparing success rates across repositories."""
    if not MATPLOTLIB_AVAILABLE:
        print("Warning: matplotlib not available. Install it or use: uv run --with matplotlib")
        return

    experiment_names = comparison['experiment_names']
    n_experiments = len(experiment_names)

    # Prepare data
    repos = []
    rates_by_experiment = {name: [] for name in experiment_names}

    for entry in comparison['by_repo']:
        # Use shortened repo name
        repo_name = entry['repo'].replace('https://github.com/', '')
        repos.append(repo_name)
        for name in experiment_names:
            rates_by_experiment[name].append(entry[name]['success_rate'])

    # Create figure with appropriate size for all repos
    fig, ax = plt.subplots(figsize=(20, 8))

    # Set up bar positions
    x = range(len(repos))
    width = 0.8 / n_experiments  # Divide available space by number of experiments

    # Color palette for N experiments
    colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22', '#95a5a6']

    # Create bars for each experiment
    bars_list = []
    for i, name in enumerate(experiment_names):
        offset = (i - n_experiments/2 + 0.5) * width
        bars = ax.bar(
            [pos + offset for pos in x],
            rates_by_experiment[name],
            width,
            label=name,
            alpha=0.8,
            color=colors[i % len(colors)]
        )
        bars_list.append((bars, rates_by_experiment[name]))

    # Customize chart
    ax.set_xlabel('Repository', fontsize=12)
    ax.set_ylabel('Success Rate (%)', fontsize=12)
    ax.set_title('Proof Verification Success Rate Comparison by Repository', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(repos, rotation=45, ha='right', fontsize=8)
    ax.legend(fontsize=10)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.set_ylim(0, 105)  # Give a little headroom above 100%

    # Add value labels on bars for non-zero values (smaller font for many experiments)
    label_fontsize = max(4, 7 - n_experiments)  # Smaller labels for more experiments
    for bars, rates in bars_list:
        for bar, rate in zip(bars, rates):
            if rate > 0:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{rate:.0f}%',
                       ha='center', va='bottom', fontsize=label_fontsize)

    # Adjust layout to prevent label cutoff
    plt.tight_layout()

    # Save figure
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"✓ Chart written to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Compare proof verification experiment analyses from experiment folders. '
                    'Loads analysis.json and run_summary.json from each folder to compare results.'
    )
    parser.add_argument(
        'experiments',
        nargs='+',
        help='Paths to experiment folders (minimum 2 required). '
             'Each folder should contain analysis.json and run_summary.json files.'
    )
    parser.add_argument(
        '--output-json',
        default='comparison.json',
        help='Path for JSON output file (default: comparison.json)'
    )
    parser.add_argument(
        '--output-md',
        default='comparison.md',
        help='Path for Markdown output file (default: comparison.md)'
    )
    parser.add_argument(
        '--chart',
        action='store_true',
        help='Generate a comparison chart (requires matplotlib)'
    )
    parser.add_argument(
        '--output-chart',
        default='comparison_chart.png',
        help='Path for chart output file (default: comparison_chart.png)'
    )

    args = parser.parse_args()

    # Validate minimum number of experiments
    experiment_folders = args.experiments
    if len(experiment_folders) < 2:
        print(f"Error: Need at least 2 experiment folders to compare, got {len(experiment_folders)}")
        exit(1)

    # Load all experiments
    print(f"Loading {len(experiment_folders)} experiments...")
    experiments = []
    for folder in experiment_folders:
        name, analysis = load_experiment_data(folder)
        experiments.append((name, analysis))

    # Compare all experiments
    print("\nComparing experiments...")
    comparison = compare_analyses(experiments)

    # Print summary to console
    print("\n" + "="*80)
    print("COMPARISON SUMMARY")
    print("="*80)

    for name, _ in experiments:
        summary = comparison['summaries'][name]
        print(f"\n{name}:")
        print(f"  Verified: {summary['total_verified']}/{summary['total_sorries']} ({summary['overall_success_rate']}%)")

    print("="*80 + "\n")

    # Write outputs
    write_json_output(comparison, args.output_json)
    write_markdown_output(comparison, args.output_md)

    # Generate chart if requested
    if args.chart:
        if not MATPLOTLIB_AVAILABLE:
            print("\nWarning: Cannot generate chart - matplotlib not available")
            print("Run with: uv run --with matplotlib compare_experiments.py ...")
        else:
            generate_chart(comparison, args.output_chart)

    print("\n✓ Comparison complete!")


if __name__ == '__main__':
    main()
