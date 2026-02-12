#!/usr/bin/env python3
"""
Pairwise scatter plot for comparing proof lengths between two strategies.

Creates a scatter plot where each point is one sorry, with one strategy's
proof length on the x-axis and another's on the y-axis. A diagonal line (y=x)
shows equality - points below mean x-axis strategy is shorter.

Usage:
    python scripts/plot_proof_lengths_scatter.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --strategies claude gemini agentic goedel \
        --subfolder 1000 \
        --x-strategy gemini \
        --y-strategy claude \
        --output charts/proof_length_scatter.pdf
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import numpy as np
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def find_sorries_solved_by_both(
    by_sorry_strategy: Dict[str, Dict[str, Any]],
    strategy_x: str,
    strategy_y: str
) -> List[str]:
    """Find sorries solved by both strategies."""
    common_sorries = []

    for sorry_id, strat_data in by_sorry_strategy.items():
        if strategy_x in strat_data and strategy_y in strat_data:
            common_sorries.append(sorry_id)

    return sorted(common_sorries)


def collect_paired_lengths(
    by_sorry_strategy: Dict[str, Dict[str, Any]],
    common_sorries: List[str],
    strategy_x: str,
    strategy_y: str
) -> Tuple[List[float], List[float]]:
    """
    Collect paired proof lengths for scatter plot.

    Returns:
        Tuple of (x_lengths, y_lengths)
    """
    x_lengths = []
    y_lengths = []

    for sorry_id in common_sorries:
        strat_data = by_sorry_strategy[sorry_id]
        x_lengths.append(strat_data[strategy_x]['avg_length'])
        y_lengths.append(strat_data[strategy_y]['avg_length'])

    return x_lengths, y_lengths


def create_scatter_plot(
    x_lengths: List[float],
    y_lengths: List[float],
    strategy_x: str,
    strategy_y: str,
    output_path: Path,
    n_sorries: int,
    log_scale: bool = False
) -> None:
    """
    Create a pairwise scatter plot comparing two strategies.

    Args:
        x_lengths: Proof lengths for x-axis strategy
        y_lengths: Proof lengths for y-axis strategy
        strategy_x: Name of x-axis strategy
        strategy_y: Name of y-axis strategy
        output_path: Path to save the plot
        n_sorries: Number of sorries
        log_scale: Whether to use log scale
    """
    if not HAS_MATPLOTLIB:
        print("Error: matplotlib is required for plotting")
        sys.exit(1)

    x = np.array(x_lengths)
    y = np.array(y_lengths)

    # Create figure
    fig, ax = plt.subplots(figsize=(10, 10))

    # Plot scatter points
    ax.scatter(x, y, alpha=0.6, s=50, c='#3498db', edgecolors='white', linewidth=0.5)

    # Draw diagonal line (y = x)
    if log_scale:
        min_val = max(1, min(x.min(), y.min()) * 0.8)
        max_val = max(x.max(), y.max()) * 1.2
    else:
        min_val = 0
        max_val = max(x.max(), y.max()) * 1.1

    ax.plot([min_val, max_val], [min_val, max_val], 'k--', linewidth=1.5, label='y = x (equal length)')

    # Apply log scale if requested
    if log_scale:
        ax.set_xscale('log')
        ax.set_yscale('log')

    # Set axis limits
    ax.set_xlim(min_val, max_val)
    ax.set_ylim(min_val, max_val)

    # Calculate statistics
    n_x_shorter = np.sum(x < y)
    n_y_shorter = np.sum(y < x)
    n_equal = np.sum(x == y)

    # Percentage
    pct_x_shorter = 100 * n_x_shorter / n_sorries
    pct_y_shorter = 100 * n_y_shorter / n_sorries

    # Labels and title
    ax.set_xlabel(f'{strategy_x} Proof Length (characters)', fontsize=12)
    ax.set_ylabel(f'{strategy_y} Proof Length (characters)', fontsize=12)

    scale_label = " (log scale)" if log_scale else ""
    ax.set_title(f'Proof Length: {strategy_x} vs {strategy_y}{scale_label}\n(n={n_sorries} sorries solved by both)', fontsize=13)

    # Add grid
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.set_axisbelow(True)

    # Add legend with statistics
    ax.legend(loc='upper left')

    # Add annotation box with statistics
    stats_text = (
        f'Points below line: {n_x_shorter} ({pct_x_shorter:.1f}%)\n'
        f'  → {strategy_x} shorter\n'
        f'Points above line: {n_y_shorter} ({pct_y_shorter:.1f}%)\n'
        f'  → {strategy_y} shorter\n'
        f'Equal: {n_equal}'
    )

    # Position in upper left, below legend
    ax.text(0.02, 0.78, stats_text, transform=ax.transAxes, fontsize=10,
            verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

    # Make sure aspect ratio is equal so diagonal is 45 degrees
    ax.set_aspect('equal', adjustable='box')

    # Tight layout and save
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"Chart saved to: {output_path}")


def print_comparison_stats(
    x_lengths: List[float],
    y_lengths: List[float],
    strategy_x: str,
    strategy_y: str
) -> None:
    """Print comparison statistics."""
    x = np.array(x_lengths)
    y = np.array(y_lengths)

    n_sorries = len(x)
    n_x_shorter = np.sum(x < y)
    n_y_shorter = np.sum(y < x)
    n_equal = np.sum(x == y)

    # Calculate differences
    diff = y - x  # positive = x is shorter

    print(f"\nComparison: {strategy_x} vs {strategy_y}")
    print("-" * 60)
    print(f"Total sorries compared: {n_sorries}")
    print(f"{strategy_x} shorter: {n_x_shorter} ({100*n_x_shorter/n_sorries:.1f}%)")
    print(f"{strategy_y} shorter: {n_y_shorter} ({100*n_y_shorter/n_sorries:.1f}%)")
    print(f"Equal length: {n_equal}")
    print()
    print(f"Mean difference ({strategy_y} - {strategy_x}): {np.mean(diff):.1f} chars")
    print(f"Median difference: {np.median(diff):.1f} chars")
    print(f"  (positive = {strategy_x} is shorter on average)")
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
        description='Create pairwise scatter plot comparing proof lengths between two strategies'
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
        help='List of strategy names to load data for'
    )
    parser.add_argument(
        '--subfolder',
        required=True,
        help='Subfolder within each strategy (e.g., "1000")'
    )
    parser.add_argument(
        '--x-strategy',
        required=True,
        help='Strategy for x-axis'
    )
    parser.add_argument(
        '--y-strategy',
        required=True,
        help='Strategy for y-axis'
    )
    parser.add_argument(
        '--output',
        default='charts/proof_length_scatter.pdf',
        help='Output chart file path (default: charts/proof_length_scatter.pdf)'
    )
    parser.add_argument(
        '--log-scale',
        action='store_true',
        help='Use log scale for both axes'
    )

    args = parser.parse_args()

    # Validate strategies
    if args.x_strategy not in args.strategies:
        print(f"Error: --x-strategy '{args.x_strategy}' must be in --strategies list")
        sys.exit(1)
    if args.y_strategy not in args.strategies:
        print(f"Error: --y-strategy '{args.y_strategy}' must be in --strategies list")
        sys.exit(1)

    # Extract proof lengths
    data = extract_proof_lengths(args.base_dir, args.strategies, args.subfolder)

    by_sorry_strategy = data['by_sorry_strategy']

    # Find sorries solved by both strategies
    common_sorries = find_sorries_solved_by_both(by_sorry_strategy, args.x_strategy, args.y_strategy)
    print(f"\nSorries solved by both {args.x_strategy} and {args.y_strategy}: {len(common_sorries)}")

    if len(common_sorries) == 0:
        print("Error: No sorries were solved by both strategies")
        sys.exit(1)

    # Collect paired lengths
    x_lengths, y_lengths = collect_paired_lengths(
        by_sorry_strategy, common_sorries, args.x_strategy, args.y_strategy
    )

    # Print comparison statistics
    print_comparison_stats(x_lengths, y_lengths, args.x_strategy, args.y_strategy)

    # Create scatter plot
    output_path = Path(args.output)
    create_scatter_plot(
        x_lengths, y_lengths, args.x_strategy, args.y_strategy,
        output_path, len(common_sorries), args.log_scale
    )


if __name__ == '__main__':
    main()
