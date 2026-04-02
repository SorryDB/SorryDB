#!/usr/bin/env python3
"""
Heatmap visualization for proof length comparison across strategies.

Creates a heatmap where rows are sorries, columns are strategies, and color
intensity represents proof length. Sorries can be sorted by a specific strategy
to reveal patterns.

Usage:
    python scripts/plot_proof_lengths_heatmap.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --strategies claude gemini agentic goedel \
        --subfolder 1000 \
        --output charts/proof_length_heatmap.pdf
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import numpy as np
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def find_sorries_solved_by_all(
    by_sorry_strategy: Dict[str, Dict[str, Any]],
    strategies: List[str]
) -> List[str]:
    """Find sorries that were solved by ALL strategies."""
    common_sorries = []
    strategy_set = set(strategies)

    for sorry_id, strat_data in by_sorry_strategy.items():
        if strategy_set.issubset(set(strat_data.keys())):
            common_sorries.append(sorry_id)

    return sorted(common_sorries)


def collect_data_matrix(
    by_sorry_strategy: Dict[str, Dict[str, Any]],
    common_sorries: List[str],
    strategies: List[str]
) -> np.ndarray:
    """
    Collect proof lengths into a 2D matrix.

    Returns:
        numpy array of shape (n_sorries, n_strategies)
    """
    result = []

    for sorry_id in common_sorries:
        strat_data = by_sorry_strategy[sorry_id]
        lengths = [strat_data[s]['avg_length'] for s in strategies]
        result.append(lengths)

    return np.array(result)


def create_heatmap(
    data: np.ndarray,
    strategies: List[str],
    output_path: Path,
    n_sorries: int,
    sort_by: Optional[str] = None,
    log_scale: bool = False
) -> None:
    """
    Create a heatmap visualization.

    Args:
        data: 2D array of shape (n_sorries, n_strategies)
        strategies: List of strategy names
        output_path: Path to save the plot
        n_sorries: Number of sorries
        sort_by: Strategy name to sort rows by (or None for no sorting)
        log_scale: Whether to use log scale for colors
    """
    if not HAS_MATPLOTLIB:
        print("Error: matplotlib is required for plotting")
        sys.exit(1)

    # Sort by specified strategy or aggregation method
    if sort_by == "median":
        # Sort by median across all strategies (robust to outliers like goedel)
        row_medians = np.median(data, axis=1)
        sort_order = np.argsort(row_medians)
        data = data[sort_order]
        sort_label = ", sorted by median"
    elif sort_by == "mean":
        # Sort by mean across all strategies
        row_means = np.mean(data, axis=1)
        sort_order = np.argsort(row_means)
        data = data[sort_order]
        sort_label = ", sorted by mean"
    elif sort_by == "min":
        # Sort by minimum across all strategies
        row_mins = np.min(data, axis=1)
        sort_order = np.argsort(row_mins)
        data = data[sort_order]
        sort_label = ", sorted by min"
    elif sort_by and sort_by in strategies:
        # Sort by a specific strategy
        sort_idx = strategies.index(sort_by)
        sort_order = np.argsort(data[:, sort_idx])
        data = data[sort_order]
        sort_label = f", sorted by {sort_by}"
    else:
        sort_label = ""

    # Apply log transform if requested
    plot_data = data.copy()
    if log_scale:
        plot_data = np.log10(np.maximum(plot_data, 1))

    # Create figure with appropriate size
    fig_height = max(8, min(20, n_sorries * 0.15))
    fig, ax = plt.subplots(figsize=(10, fig_height))

    # Create heatmap
    cmap = 'viridis'
    im = ax.imshow(plot_data, aspect='auto', cmap=cmap)

    # Set ticks and labels
    ax.set_xticks(range(len(strategies)))
    ax.set_xticklabels(strategies, fontsize=11)

    # For y-axis, show fewer ticks if many sorries
    if n_sorries > 50:
        # Show tick every N sorries
        tick_interval = max(1, n_sorries // 20)
        ax.set_yticks(range(0, n_sorries, tick_interval))
        ax.set_yticklabels(range(0, n_sorries, tick_interval), fontsize=8)
    else:
        ax.set_yticks(range(n_sorries))
        ax.set_yticklabels(range(n_sorries), fontsize=8)

    # Labels and title
    ax.set_xlabel('Strategy', fontsize=12)
    ax.set_ylabel('Sorry Index', fontsize=12)

    if log_scale:
        title = f'Proof Length Heatmap (n={n_sorries}{sort_label}, log scale)'
    else:
        title = f'Proof Length Heatmap (n={n_sorries} sorries{sort_label})'
    ax.set_title(title, fontsize=13)

    # Add colorbar
    cbar = plt.colorbar(im, ax=ax, pad=0.02)
    if log_scale:
        cbar.set_label('log₁₀(Proof Length)', fontsize=11)
    else:
        cbar.set_label('Proof Length (characters)', fontsize=11)

    # Tight layout and save
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"Chart saved to: {output_path}")


def print_summary_stats(
    data: np.ndarray,
    strategies: List[str]
) -> None:
    """Print summary statistics for each strategy."""
    print("\nSummary Statistics (for sorries solved by all strategies):")
    print("-" * 60)
    print(f"{'Strategy':<15} {'Median':>10} {'Mean':>10} {'Std Dev':>10}")
    print("-" * 60)

    for i, strategy in enumerate(strategies):
        col = data[:, i]
        median = np.median(col)
        mean = np.mean(col)
        std = np.std(col)
        print(f"{strategy:<15} {median:>10.1f} {mean:>10.1f} {std:>10.1f}")

    print("-" * 60)


def extract_proof_lengths(base_dir: str, strategies: List[str], subfolder: str) -> Dict[str, Any]:
    """Call extract_proof_lengths.py and return the extracted data."""
    script_path = Path(__file__).parent / "extract_proof_lengths.py"

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_output = f.name

    try:
        cmd = [
            sys.executable,
            str(script_path),
            '--base-dir', base_dir,
            '--strategies', *strategies,
            '--subfolder', subfolder,
            '--output', temp_output
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            sys.exit(result.returncode)

        # Print the extraction output
        print(result.stdout, end='')

        with open(temp_output, 'r') as f:
            return json.load(f)
    finally:
        Path(temp_output).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(
        description='Create heatmap for proof length comparison'
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
        default='charts/proof_length_heatmap.pdf',
        help='Output chart file path (default: charts/proof_length_heatmap.pdf)'
    )
    parser.add_argument(
        '--sort-by',
        help='Sort rows by: "median" (across strategies, robust to outliers), '
             '"mean", "min", or a strategy name'
    )
    parser.add_argument(
        '--log-scale',
        action='store_true',
        help='Use log scale for color intensity'
    )

    args = parser.parse_args()

    # Extract proof lengths
    data = extract_proof_lengths(args.base_dir, args.strategies, args.subfolder)

    by_sorry_strategy = data['by_sorry_strategy']
    strategies = data['metadata']['strategies']

    print(f"\nStrategies: {strategies}")

    # Find sorries solved by ALL strategies
    common_sorries = find_sorries_solved_by_all(by_sorry_strategy, strategies)
    print(f"Sorries solved by all {len(strategies)} strategies: {len(common_sorries)}")

    if len(common_sorries) == 0:
        print("Error: No sorries were solved by all strategies")
        sys.exit(1)

    # Collect data matrix
    data_matrix = collect_data_matrix(by_sorry_strategy, common_sorries, strategies)

    # Print summary statistics
    print_summary_stats(data_matrix, strategies)

    # Create heatmap
    output_path = Path(args.output)
    create_heatmap(
        data_matrix, strategies, output_path, len(common_sorries),
        sort_by=args.sort_by, log_scale=args.log_scale
    )


if __name__ == '__main__':
    main()
