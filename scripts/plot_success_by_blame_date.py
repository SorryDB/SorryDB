#!/usr/bin/env python3
"""
Plot success rate by blame date for multiple theorem prover strategies.

Creates a line plot showing the percentage of solved sorries over time,
with one line per strategy. Blame dates are binned into 2-week intervals.

Usage:
    python scripts/plot_success_by_blame_date.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --strategies claude gemini goedel multi_tactic \
        --subfolder 1000 \
        --output charts/success_by_blame_date.pdf
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Set font to match paper style
plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.serif'] = ['Times New Roman']

# Strategy colors (consistent with other scripts)
STRATEGY_COLORS = {
    "claude": "#AEC7E8",       # Light Blue
    "gemini": "#C5B0D5",       # Light Purple
    "goedel": "#9467BD",       # Purple
    "gpt": "#98DF8A",          # Light Green
    "multi_tactic": "#17BECF", # Teal
    "agentic": "#FF9896",      # Light Red
    "goedel_agentic": "#FF7F0E",  # Orange
    "gemini_agentic": "#D62728",  # Red
}

# Fallback colors if strategy not in map
FALLBACK_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
]

# Strategy markers for line plots
STRATEGY_MARKERS = {
    "claude": "o",
    "gemini": "s",
    "goedel": "^",
    "gpt": "D",
    "multi_tactic": "v",
    "agentic": "p",
    "goedel_agentic": "h",
    "gemini_agentic": "*",
}


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


def load_sorries_with_blame_dates(result_json_path: Path) -> List[Dict]:
    """
    Load all sorries with their blame_date and proof_verified status.

    Args:
        result_json_path: Path to result.json file

    Returns:
        List of dicts with 'blame_date' (datetime) and 'verified' (bool)
    """
    with open(result_json_path, 'r') as f:
        data = json.load(f)

    sorries = []
    for entry in data:
        blame_date_str = entry.get('sorry', {}).get('metadata', {}).get('blame_date')
        if not blame_date_str:
            continue

        try:
            blame_date = datetime.fromisoformat(blame_date_str)
            # Strip timezone info for consistency
            if blame_date.tzinfo:
                blame_date = blame_date.replace(tzinfo=None)

            sorries.append({
                'blame_date': blame_date,
                'verified': entry.get('proof_verified', False)
            })
        except ValueError as e:
            print(f"Warning: Could not parse date '{blame_date_str}': {e}")

    return sorries


def compute_date_range(all_sorries: Dict[str, List[Dict]]) -> Tuple[datetime, datetime]:
    """
    Compute the overall date range across all strategies.

    Args:
        all_sorries: Dict mapping strategy name to list of sorries

    Returns:
        Tuple of (min_date, max_date)
    """
    all_dates = []
    for sorries in all_sorries.values():
        for s in sorries:
            all_dates.append(s['blame_date'])

    if not all_dates:
        return datetime.now(), datetime.now()

    return min(all_dates), max(all_dates)


def create_bins(min_date: datetime, max_date: datetime, interval_days: int = 14) -> List[datetime]:
    """
    Create bin edges for the given date range.

    Args:
        min_date: Start of date range
        max_date: End of date range
        interval_days: Days per bin (default 14 = 2 weeks)

    Returns:
        List of bin edge datetimes
    """
    # Round min_date down to start of week
    days_since_monday = min_date.weekday()
    bin_start = min_date - timedelta(days=days_since_monday)
    bin_start = bin_start.replace(hour=0, minute=0, second=0, microsecond=0)

    bins = []
    current = bin_start
    while current <= max_date + timedelta(days=interval_days):
        bins.append(current)
        current += timedelta(days=interval_days)

    return bins


def bin_sorries(
    sorries: List[Dict],
    bins: List[datetime]
) -> Dict[datetime, Dict[str, int]]:
    """
    Bin sorries into intervals and compute stats per bin.

    Args:
        sorries: List of sorries with 'blame_date' and 'verified'
        bins: List of bin edge datetimes

    Returns:
        Dict mapping bin_start -> {'total': N, 'verified': M}
    """
    bin_stats = {bins[i]: {'total': 0, 'verified': 0} for i in range(len(bins) - 1)}

    for sorry in sorries:
        blame_date = sorry['blame_date']
        # Find which bin this sorry belongs to
        for i in range(len(bins) - 1):
            if bins[i] <= blame_date < bins[i + 1]:
                bin_stats[bins[i]]['total'] += 1
                if sorry['verified']:
                    bin_stats[bins[i]]['verified'] += 1
                break

    return bin_stats


def plot_success_by_date(
    strategy_stats: Dict[str, Dict[datetime, Dict[str, int]]],
    output_path: str | None = None
) -> None:
    """
    Create line plot with one line per strategy.

    Args:
        strategy_stats: Dict mapping strategy -> bin_start -> {'total', 'verified'}
        output_path: Optional path to save the plot
    """
    fig, ax = plt.subplots(figsize=(12, 6))

    color_idx = 0
    for strategy, bin_stats in strategy_stats.items():
        # Get sorted bin dates
        bin_dates = sorted(bin_stats.keys())

        # Compute success rates, only for bins with data
        dates_with_data = []
        success_rates = []
        for bin_date in bin_dates:
            total = bin_stats[bin_date]['total']
            if total > 0:
                verified = bin_stats[bin_date]['verified']
                success_rate = (verified / total) * 100
                dates_with_data.append(bin_date)
                success_rates.append(success_rate)

        if not dates_with_data:
            continue

        # Get color and marker for this strategy
        color = STRATEGY_COLORS.get(strategy, FALLBACK_COLORS[color_idx % len(FALLBACK_COLORS)])
        marker = STRATEGY_MARKERS.get(strategy, 'o')
        color_idx += 1

        # Plot line
        ax.plot(
            dates_with_data,
            success_rates,
            marker=marker,
            label=strategy,
            color=color,
            linewidth=2,
            markersize=8,
            alpha=0.8
        )

    # Format axes
    ax.set_xlabel("Blame Date", fontsize=16)
    ax.set_ylabel("Success Rate (%)", fontsize=16)
    ax.set_ylim(0, 100)

    # Format x-axis as dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=12)
    ax.tick_params(axis='y', labelsize=12)

    # Remove top and right spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Add legend
    ax.legend(loc='upper left', fontsize=12, frameon=False)

    # Add grid for readability
    ax.grid(axis='y', alpha=0.3, linestyle='--')

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Plot saved to {output_path}")
    else:
        plt.show()

    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description='Plot success rate by blame date for multiple strategies'
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
        '-o',
        help='Output file path for the plot (PDF or PNG)'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=91,
        help='Bin interval in days (default: 91 = ~3 months)'
    )

    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        print(f"Error: Base directory does not exist: {base_dir}")
        sys.exit(1)

    # Discover experiment directories for each strategy
    print(f"Discovering experiments in {base_dir}...")
    experiment_dirs: Dict[str, Path] = {}

    for strategy in args.strategies:
        experiment_dir = discover_experiment_for_strategy(base_dir, strategy, args.subfolder)
        print(f"  {strategy}: {experiment_dir.name}")
        experiment_dirs[strategy] = experiment_dir

    print()

    # Load sorries with blame dates for each strategy
    print("Loading sorries with blame dates...")
    all_sorries: Dict[str, List[Dict]] = {}

    for strategy, exp_dir in experiment_dirs.items():
        result_json = exp_dir / "result.json"
        if not result_json.exists():
            print(f"  Warning: No result.json found for {strategy}")
            continue

        sorries = load_sorries_with_blame_dates(result_json)
        all_sorries[strategy] = sorries
        verified_count = sum(1 for s in sorries if s['verified'])
        print(f"  {strategy}: {len(sorries)} sorries ({verified_count} verified)")

    print()

    # Compute common date range and bins
    min_date, max_date = compute_date_range(all_sorries)
    print(f"Date range: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}")

    bins = create_bins(min_date, max_date, args.interval)
    print(f"Created {len(bins) - 1} bins of {args.interval} days each")
    print()

    # Bin sorries for each strategy
    strategy_stats: Dict[str, Dict[datetime, Dict[str, int]]] = {}
    for strategy, sorries in all_sorries.items():
        strategy_stats[strategy] = bin_sorries(sorries, bins)

    # Plot
    plot_success_by_date(strategy_stats, args.output)


if __name__ == '__main__':
    main()
