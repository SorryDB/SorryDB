#!/usr/bin/env python3
"""
Parallel coordinates plot for proof length comparison across strategies.

Creates a plot where each line represents one sorry, connecting its proof lengths
across all strategies. This allows visual comparison of how the same sorry's
proof length varies between strategies.

Usage:
    python scripts/plot_proof_lengths_parallel.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --strategies claude gemini agentic goedel \
        --subfolder 1000 \
        --output charts/proof_length_parallel.pdf
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
    from matplotlib.collections import LineCollection
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


def collect_data_for_parallel_plot(
    by_sorry_strategy: Dict[str, Dict[str, Any]],
    common_sorries: List[str],
    strategies: List[str]
) -> List[List[float]]:
    """
    Collect proof lengths for each sorry across all strategies.

    Returns:
        List of lists, where each inner list contains the avg_length
        for one sorry across all strategies (in order).
    """
    result = []

    for sorry_id in common_sorries:
        strat_data = by_sorry_strategy[sorry_id]
        lengths = [strat_data[s]['avg_length'] for s in strategies]
        result.append(lengths)

    return result


def create_parallel_coordinates_plot(
    data: List[List[float]],
    strategies: List[str],
    output_path: Path,
    n_sorries: int,
    log_scale: bool = False,
    max_length: Optional[float] = None
) -> None:
    """
    Create a parallel coordinates plot.

    Args:
        data: List of lists, each containing proof lengths across strategies
        strategies: List of strategy names (determines x-axis order)
        output_path: Path to save the plot
        n_sorries: Number of sorries (for title)
        log_scale: Whether to use log scale for y-axis
        max_length: Optional maximum y-axis value (cuts off outliers)
    """
    if not HAS_MATPLOTLIB:
        print("Error: matplotlib is required for plotting")
        sys.exit(1)

    fig, ax = plt.subplots(figsize=(12, 8))

    # X positions for each strategy
    x_positions = list(range(len(strategies)))

    # Convert data to numpy for easier manipulation
    data_array = np.array(data)

    if log_scale:
        # Apply log transform, handling zeros
        data_array = np.log10(np.maximum(data_array, 1))

    # Calculate median for coloring
    median_lengths = np.median(data_array, axis=1)

    # Normalize for colormap
    norm = plt.Normalize(median_lengths.min(), median_lengths.max())
    cmap = plt.cm.viridis

    # Create line segments for LineCollection (more efficient than individual plots)
    segments = []
    colors = []

    for i, row in enumerate(data_array):
        points = list(zip(x_positions, row))
        for j in range(len(points) - 1):
            segments.append([points[j], points[j + 1]])
            colors.append(cmap(norm(median_lengths[i])))

    # Create LineCollection
    lc = LineCollection(segments, colors=colors, alpha=0.4, linewidths=1)
    ax.add_collection(lc)

    # Calculate and plot median line
    medians = np.median(data_array, axis=0)
    ax.plot(x_positions, medians, 'r-', linewidth=3, label='Median', zorder=10)

    # Calculate and plot mean line
    means = np.mean(data_array, axis=0)
    ax.plot(x_positions, means, 'b--', linewidth=2, label='Mean', zorder=10)

    # Set axis properties
    ax.set_xticks(x_positions)
    ax.set_xticklabels(strategies, fontsize=11)
    ax.set_xlim(-0.5, len(strategies) - 0.5)

    # Set y limits with some padding
    y_min = data_array.min()
    if max_length is not None:
        y_max = max_length
        # Count how many lines are clipped
        n_clipped = np.sum(np.any(data_array > max_length, axis=1))
        clip_info = f", {n_clipped} clipped"
    else:
        y_max = data_array.max()
        clip_info = ""
    y_padding = (y_max - y_min) * 0.05
    ax.set_ylim(y_min - y_padding, y_max + y_padding)

    # Labels and title
    if log_scale:
        ax.set_ylabel('Proof Length (log₁₀ characters)')
        title = f'Parallel Coordinates: Proof Lengths (n={n_sorries}, log scale)'
    elif max_length is not None:
        ax.set_ylabel('Proof Length (characters)')
        title = f'Parallel Coordinates: Proof Lengths (n={n_sorries}{clip_info}, max={int(max_length)})'
    else:
        ax.set_ylabel('Proof Length (characters)')
        title = f'Parallel Coordinates: Proof Lengths (n={n_sorries} sorries solved by all)'

    ax.set_xlabel('Strategy')
    ax.set_title(title)

    # Add grid
    ax.yaxis.grid(True, linestyle='--', alpha=0.5)
    ax.set_axisbelow(True)

    # Add legend
    ax.legend(loc='upper right')

    # Add colorbar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = plt.colorbar(sm, ax=ax, pad=0.02)
    if log_scale:
        cbar.set_label('Median log₁₀(length) across strategies')
    else:
        cbar.set_label('Median length across strategies')

    # Tight layout and save
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"Chart saved to: {output_path}")


def print_summary_stats(
    data: List[List[float]],
    strategies: List[str]
) -> None:
    """Print summary statistics for each strategy."""
    data_array = np.array(data)

    print("\nSummary Statistics (for sorries solved by all strategies):")
    print("-" * 60)
    print(f"{'Strategy':<15} {'Median':>10} {'Mean':>10} {'Std Dev':>10}")
    print("-" * 60)

    for i, strategy in enumerate(strategies):
        col = data_array[:, i]
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
        description='Create parallel coordinates plot for proof length comparison'
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
        default='charts/proof_length_parallel.pdf',
        help='Output chart file path (default: charts/proof_length_parallel.pdf)'
    )
    parser.add_argument(
        '--log-scale',
        action='store_true',
        help='Use log scale for proof lengths'
    )
    parser.add_argument(
        '--max-length',
        type=float,
        help='Maximum y-axis value (cuts off outliers above this threshold)'
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

    # Collect data for parallel coordinates
    plot_data = collect_data_for_parallel_plot(by_sorry_strategy, common_sorries, strategies)

    # Print summary statistics
    print_summary_stats(plot_data, strategies)

    # Create parallel coordinates plot
    output_path = Path(args.output)
    create_parallel_coordinates_plot(
        plot_data, strategies, output_path, len(common_sorries),
        log_scale=args.log_scale, max_length=args.max_length
    )


if __name__ == '__main__':
    main()
