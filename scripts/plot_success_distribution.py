#!/usr/bin/env python3
"""
Plot distribution of successful attempts per sorry for pass@k experiments.

Generates two visualizations:
1. Small multiples: Separate histogram for each strategy (normalized to %)
2. CDF: Cumulative distribution showing % of sorries solved at least X times

Usage:
    python scripts/plot_success_distribution.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --strategies claude gemini goedel \
        --subfolder 1000 \
        --output-histograms success_histograms.png \
        --output-cdf success_cdf.png
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np


def derive_experiment_name_from_summary(folder_path: Path, run_summary: Dict[str, Any]) -> str:
    """
    Derive experiment name from run_summary.json metadata.
    (Same logic as compare_experiments.py)

    For non-LLM strategies: Returns strategy name (e.g., 'rfl', 'supersimple')
    For LLM strategies: Returns model name (e.g., 'gemini-3-flash-preview', 'claude-3-7-sonnet')
    """
    try:
        strategy_name = run_summary['strategy']['name']

        # For LLM strategies, use the model name or provider name
        if strategy_name == 'llm':
            try:
                # First try to get the model name
                model = run_summary['strategy']['args']['model_config']['params']['model']
                return model
            except KeyError:
                # Fallback: try to get the provider name (for goedel, deepseek, etc.)
                try:
                    provider = run_summary['strategy']['args']['model_config']['provider']
                    # Map provider names to display names
                    provider_display_names = {
                        'goedel': 'Goedel-Prover-V2-32B',
                    }
                    return provider_display_names.get(provider, provider)
                except KeyError:
                    # Last resort: extract from parent directory name
                    parent_dir = folder_path.parent.name
                    print(f"Warning: Could not find model or provider in run_summary.json, using parent directory: {parent_dir}")
                    return parent_dir

        # For agentic strategies, append the model name to disambiguate
        if strategy_name == 'agentic':
            try:
                model = run_summary['strategy']['args']['model']
                # Clean up model name (e.g., "google_genai:gemini-3-flash-preview" -> "gemini-3-flash-preview")
                if ':' in model:
                    model = model.split(':')[-1]
                return f"{model} (self-correction)"
            except KeyError:
                pass  # Fall through to return just "agentic"

        # For non-LLM strategies, return strategy name (with display name mapping)
        display_names = {
            'multi_tactic': 'multi-tactic',
            'goedel': 'Goedel-Prover-V2-32B',
        }
        return display_names.get(strategy_name, strategy_name)

    except KeyError as e:
        print(f"Error: Missing key {e} in run_summary.json for {folder_path}")
        # Fallback to folder name
        return folder_path.name


def load_run_summary(experiment_dir: Path) -> Dict[str, Any]:
    """Load run_summary.json from experiment directory."""
    run_summary_path = experiment_dir / "run_summary.json"
    if not run_summary_path.exists():
        raise FileNotFoundError(f"run_summary.json not found in {experiment_dir}")

    with open(run_summary_path) as f:
        return json.load(f)


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
        # Sort by directory name (timestamp format YYYY-MM-DD_HH-MM-SS_*) and pick most recent
        experiment_dirs = sorted(experiment_dirs, key=lambda d: d.name)
        print(f"  Note: Multiple experiments found, using most recent: {experiment_dirs[-1].name}")
        return experiment_dirs[-1]

    return experiment_dirs[0]


def load_pass_at_k_results(experiment_dir: Path) -> Dict:
    """Load pass_at_k_results.json from experiment directory."""
    results_path = experiment_dir / "pass_at_k_results.json"
    if not results_path.exists():
        raise FileNotFoundError(f"pass_at_k_results.json not found in {experiment_dir}")

    with open(results_path) as f:
        return json.load(f)


def compute_success_counts(results: Dict[str, List[int]], only_solved: bool = True) -> List[int]:
    """
    Count successful attempts per sorry.

    Args:
        results: Dict mapping sorry_id -> array of 0/1 for each attempt
        only_solved: If True, only include sorries that were solved at least once

    Returns:
        List of integers, each representing the count of successful attempts
        for a single sorry (1 to k if only_solved, else 0 to k)
    """
    counts = [sum(arr) for arr in results.values()]
    if only_solved:
        counts = [c for c in counts if c > 0]
    return counts


def get_color(label: str, index: int) -> str:
    """Get color for a label, with fallback."""
    custom_colors = {
        "combined":                         "#333333",  # Dark Gray
        "claude-opus-4-5 (self-correction)": "#1F77B4",  # Dark Blue
        "claude-opus-4-5":                  "#AEC7E8",  # Light Blue
        "gemini-3-pro-preview":             "#2CA02C",  # Dark Green
        "gemini-3-flash-preview (self-correction)": "#2CA02C",  # Dark Green
        "gemini-3-flash-preview":           "#98DF8A",  # Light Green
        "Goedel-Prover-V2-32B":             "#9467BD",  # Purple
        "multi-tactic":                     "#17BECF",  # Teal
    }
    fallback_colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22', '#95a5a6']
    return custom_colors.get(label, fallback_colors[index % len(fallback_colors)])


def plot_small_multiples(
    data: List[Tuple[str, List[int]]],
    k_value: int,
    output_path: Path,
    title: str | None = None
):
    """
    Plot small multiples (faceted histograms) for each strategy.

    Args:
        data: List of (label, success_counts) tuples
        k_value: Number of attempts (e.g., 32)
        output_path: Path to save the plot
        title: Optional overall title
    """
    plt.rcParams['font.family'] = 'serif'
    plt.rcParams['font.serif'] = ['Times New Roman']

    n_strategies = len(data)
    # Arrange in a grid (prefer 2 columns)
    n_cols = min(2, n_strategies)
    n_rows = math.ceil(n_strategies / n_cols)

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(6 * n_cols, 4 * n_rows), squeeze=False)

    # Bin edges: 1, 2, ..., k, k+1
    bin_edges = list(range(1, k_value + 2))

    # Find global max for consistent y-axis (as percentage)
    max_pct = 0
    for label, counts in data:
        hist, _ = np.histogram(counts, bins=bin_edges)
        pct = hist / len(counts) * 100
        max_pct = max(max_pct, pct.max())

    for idx, (label, counts) in enumerate(data):
        row = idx // n_cols
        col = idx % n_cols
        ax = axes[row, col]

        color = get_color(label, idx)

        # Plot histogram as percentage
        ax.hist(
            counts,
            bins=bin_edges,
            weights=np.ones(len(counts)) / len(counts) * 100,
            color=color,
            edgecolor='white',
            linewidth=0.5,
            alpha=0.8,
        )

        ax.set_title(f"{label} (n={len(counts)})", fontsize=14, fontweight='bold')
        ax.set_xlabel(f'Successes (out of {k_value})', fontsize=12)
        ax.set_ylabel('% of Solved Sorries', fontsize=12)

        # Consistent y-axis across all subplots
        ax.set_ylim(0, max_pct * 1.1)

        # X-axis ticks
        tick_step = max(1, k_value // 8)
        ax.set_xticks(range(1, k_value + 1, tick_step))
        ax.tick_params(axis='both', labelsize=10)

        ax.grid(axis='y', alpha=0.3, linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

    # Hide empty subplots
    for idx in range(n_strategies, n_rows * n_cols):
        row = idx // n_cols
        col = idx % n_cols
        axes[row, col].set_visible(False)

    if title:
        fig.suptitle(title, fontsize=16, fontweight='bold', y=1.02)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Small multiples plot saved to: {output_path}")


def plot_cdf(
    data: List[Tuple[str, List[int]]],
    k_value: int,
    output_path: Path,
    title: str | None = None
):
    """
    Plot cumulative distribution function (CDF) for each strategy.

    Shows what percentage of solved sorries are solved at least X times.

    Args:
        data: List of (label, success_counts) tuples
        k_value: Number of attempts (e.g., 32)
        output_path: Path to save the plot
        title: Optional title
    """
    plt.rcParams['font.family'] = 'serif'
    plt.rcParams['font.serif'] = ['Times New Roman']

    fig, ax = plt.subplots(figsize=(10, 6))

    x = np.arange(1, k_value + 1)

    for idx, (label, counts) in enumerate(data):
        color = get_color(label, idx)

        # Compute CDF: % of sorries with at least x successes
        cdf = []
        n = len(counts)
        for threshold in x:
            pct = sum(1 for c in counts if c >= threshold) / n * 100
            cdf.append(pct)

        ax.plot(x, cdf, marker='o', markersize=4, label=f"{label} (n={n})",
                color=color, linewidth=2)

    ax.set_xlabel(f'Minimum Successes (out of {k_value})', fontsize=20)
    ax.set_ylabel('% of Solved Sorries', fontsize=20)
    if title:
        ax.set_title(title, fontsize=14, fontweight='bold')

    # Legend at top
    ax.legend(bbox_to_anchor=(0.5, 1.15), loc='upper center', ncol=2, frameon=False, fontsize=14)

    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    ax.tick_params(axis='x', labelsize=18)
    ax.tick_params(axis='y', labelsize=16)

    # X-axis ticks
    tick_step = max(1, k_value // 8)
    ax.set_xticks(range(1, k_value + 1, tick_step))

    ax.set_ylim(0, 105)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"CDF plot saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Plot distribution of successful attempts per sorry for pass@k experiments'
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
        '--output-histograms',
        type=Path,
        default=Path('success_histograms.png'),
        help='Output file path for small multiples histograms (default: success_histograms.png)'
    )
    parser.add_argument(
        '--output-cdf',
        type=Path,
        default=Path('success_cdf.png'),
        help='Output file path for CDF plot (default: success_cdf.png)'
    )
    parser.add_argument(
        '--title',
        default=None,
        help='Plot title (optional)'
    )
    parser.add_argument(
        '--labels',
        nargs='+',
        help='Custom labels for each strategy (must match number of strategies)'
    )

    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        print(f"Error: Base directory does not exist: {base_dir}")
        sys.exit(1)

    # Validate labels if provided
    if args.labels and len(args.labels) != len(args.strategies):
        print(f"Error: Number of labels ({len(args.labels)}) must match number of strategies ({len(args.strategies)})")
        sys.exit(1)

    # Discover experiment directories for each strategy
    print(f"Discovering experiments in {base_dir}...")
    experiment_dirs: List[Path] = []

    for strategy in args.strategies:
        experiment_dir = discover_experiment_for_strategy(base_dir, strategy, args.subfolder)
        print(f"  {strategy}: {experiment_dir.name}")
        experiment_dirs.append(experiment_dir)

    print()

    # Load pass@k results and compute success counts
    plot_data: List[Tuple[str, List[int]]] = []
    k_value = None

    for strategy, exp_dir in zip(args.strategies, experiment_dirs):
        try:
            data = load_pass_at_k_results(exp_dir)
        except FileNotFoundError as e:
            print(f"Error: {e}")
            print(f"Run extract_pass_at_k.py first to generate the data.")
            sys.exit(1)

        # Derive label from run_summary.json
        try:
            run_summary = load_run_summary(exp_dir)
            label = derive_experiment_name_from_summary(exp_dir, run_summary)
        except FileNotFoundError:
            label = strategy  # Fallback to strategy name

        if k_value is None:
            k_value = data["k"]
        elif data["k"] != k_value:
            print(f"Warning: {strategy} has k={data['k']}, expected k={k_value}")

        # Get all counts (including unsolved) for statistics
        all_counts = compute_success_counts(data["results"], only_solved=False)
        # Get only solved counts for plotting
        success_counts = compute_success_counts(data["results"], only_solved=True)
        plot_data.append((label, success_counts))

        # Print summary statistics
        total_sorries = len(all_counts)
        solved_sorries = len(success_counts)
        avg_successes = sum(success_counts) / solved_sorries if solved_sorries > 0 else 0
        always_solved = sum(1 for c in success_counts if c == k_value)
        print(f"  {label}:")
        print(f"    Total sorries: {total_sorries}")
        print(f"    Solved at least once: {solved_sorries}")
        print(f"    Average successes (among solved): {avg_successes:.2f} / {k_value}")
        print(f"    Always solved ({k_value}/{k_value}): {always_solved}")

    # Override with custom labels if provided
    if args.labels:
        plot_data = [(label, counts) for (_, counts), label in zip(plot_data, args.labels)]

    print()

    # Generate both plots
    plot_small_multiples(plot_data, k_value, args.output_histograms, args.title)
    plot_cdf(plot_data, k_value, args.output_cdf, args.title)


if __name__ == '__main__':
    main()
