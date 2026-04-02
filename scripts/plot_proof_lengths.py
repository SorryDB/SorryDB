#!/usr/bin/env python3
"""
Plot proof length comparison across strategies.

Creates a box plot comparing proof lengths for sorries solved by ALL strategies,
ensuring an apples-to-apples comparison.

Usage:
    python scripts/plot_proof_lengths.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --strategies claude gemini agentic goedel \
        --subfolder 1000 \
        --output charts/proof_length_comparison.pdf
"""

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# Strategy colors (consistent with other scripts)
STRATEGY_COLORS = {
    "combined":                         "#333333",  # Dark Gray
    "claude-opus-4-5 (self-correction)": "#1F77B4",  # Dark Blue
    "claude-opus-4-5":                  "#AEC7E8",  # Light Blue
    "gemini-3-pro-preview":             "#2CA02C",  # Dark Green
    "gemini-3-flash-preview (self-correction)": "#2CA02C",  # Dark Green
    "gemini-3-flash-preview":           "#98DF8A",  # Light Green
    "Goedel-Prover-V2-32B":             "#9467BD",  # Purple
    "multi-tactic":                     "#17BECF",  # Teal
}

# Fallback colors if strategy not in map
FALLBACK_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
]


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


def find_sorries_solved_by_all(
    by_sorry_strategy: Dict[str, Dict[str, Any]],
    strategies: List[str]
) -> List[str]:
    """
    Find sorries that were solved by ALL strategies.

    Args:
        by_sorry_strategy: Dict mapping sorry_id -> strategy -> length_data
        strategies: List of strategy names to check

    Returns:
        List of sorry IDs solved by all strategies
    """
    common_sorries = []
    strategy_set = set(strategies)

    for sorry_id, strat_data in by_sorry_strategy.items():
        if strategy_set.issubset(set(strat_data.keys())):
            common_sorries.append(sorry_id)

    return sorted(common_sorries)


def collect_lengths_for_common_sorries(
    by_sorry_strategy: Dict[str, Dict[str, Any]],
    common_sorries: List[str],
    strategies: List[str]
) -> Dict[str, List[float]]:
    """
    Collect proof lengths for each strategy, only for common sorries.

    Args:
        by_sorry_strategy: Dict mapping sorry_id -> strategy -> length_data
        common_sorries: List of sorry IDs to include
        strategies: List of strategy names

    Returns:
        Dict mapping strategy -> list of avg_lengths
    """
    result: Dict[str, List[float]] = {s: [] for s in strategies}

    for sorry_id in common_sorries:
        strat_data = by_sorry_strategy[sorry_id]
        for strategy in strategies:
            avg_length = strat_data[strategy]['avg_length']
            result[strategy].append(avg_length)

    return result


def create_box_plot(
    lengths_by_strategy: Dict[str, List[float]],
    strategies: List[str],
    display_names: Dict[str, str],
    output_path: Path,
    n_sorries: int,
    log_scale: bool = False
) -> None:
    """
    Create a box plot comparing proof lengths across strategies.

    Args:
        lengths_by_strategy: Dict mapping strategy -> list of proof lengths
        strategies: List of strategy names (determines order)
        display_names: Dict mapping strategy -> display name
        output_path: Path to save the plot
        n_sorries: Number of common sorries (for title)
        log_scale: Whether to use log scale for y-axis
    """
    if not HAS_MATPLOTLIB:
        print("Error: matplotlib is required for plotting")
        sys.exit(1)

    # Set font to match paper style
    plt.rcParams['font.family'] = 'serif'
    plt.rcParams['font.serif'] = ['Times New Roman']

    # Prepare data for box plot using display names
    labels = [display_names.get(s, s) for s in strategies]
    data = [lengths_by_strategy[s] for s in strategies]

    # Create figure
    fig, ax = plt.subplots(figsize=(10, 6))

    # Create box plot
    bp = ax.boxplot(data, tick_labels=labels, patch_artist=True)

    # Style the boxes with consistent colors
    for i, (box, strategy) in enumerate(zip(bp['boxes'], strategies)):
        label = display_names.get(strategy, strategy)
        color = STRATEGY_COLORS.get(label, FALLBACK_COLORS[i % len(FALLBACK_COLORS)])
        box.set_facecolor(color)
        box.set_alpha(0.7)

    # Add median annotations
    for i, (median_line, strategy) in enumerate(zip(bp['medians'], strategies)):
        median_val = median_line.get_ydata()[0]
        ax.annotate(
            f'{median_val:.0f}',
            xy=(i + 1, median_val),
            xytext=(5, 5),
            textcoords='offset points',
            fontsize=9,
            color='black'
        )

    # Apply log scale if requested
    if log_scale:
        ax.set_yscale('log')
        ax.set_ylabel('Proof Length (characters, log scale)', fontsize=14)
        ax.set_title(f'Proof Length Comparison (n={n_sorries} sorries, log scale)', fontsize=14, fontweight='bold')
    else:
        ax.set_ylabel('Proof Length (characters)', fontsize=14)
        ax.set_title(f'Proof Length Comparison (n={n_sorries} sorries solved by all strategies)', fontsize=14, fontweight='bold')

    ax.set_xlabel('Strategy', fontsize=14)

    # Add grid for readability
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)

    # Remove top and right spines (matching other scripts)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Tick label sizes and rotation to prevent overlap
    ax.tick_params(axis='x', labelsize=10)
    ax.tick_params(axis='y', labelsize=12)
    plt.xticks(rotation=20, ha='right')

    # Tight layout and save
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"Chart saved to: {output_path}")


def print_summary_stats(
    lengths_by_strategy: Dict[str, List[float]],
    strategies: List[str],
    display_names: Dict[str, str]
) -> None:
    """Print summary statistics for each strategy."""
    print("\nSummary Statistics:")
    print("-" * 80)
    print(f"{'Strategy':<35} {'Median':>10} {'Mean':>10} {'Std Dev':>10} {'Min':>8} {'Max':>8}")
    print("-" * 80)

    for strategy in strategies:
        label = display_names.get(strategy, strategy)
        lengths = lengths_by_strategy[strategy]
        median = statistics.median(lengths)
        mean = statistics.mean(lengths)
        stdev = statistics.stdev(lengths) if len(lengths) > 1 else 0
        min_val = min(lengths)
        max_val = max(lengths)
        print(f"{label:<35} {median:>10.1f} {mean:>10.1f} {stdev:>10.1f} {min_val:>8.0f} {max_val:>8.0f}")

    print("-" * 80)


def extract_proof_lengths(base_dir: str, strategies: List[str], subfolder: str) -> Dict[str, Any]:
    """
    Call extract_proof_lengths.py and return the extracted data.

    Args:
        base_dir: Base directory containing strategy folders
        strategies: List of strategy names
        subfolder: Subfolder within each strategy

    Returns:
        Dict with proof length data
    """
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
        description='Plot proof length comparison across strategies'
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
        default='charts/proof_length_comparison.pdf',
        help='Output chart file path (default: charts/proof_length_comparison.pdf)'
    )
    parser.add_argument(
        '--log-scale',
        action='store_true',
        help='Use log scale for y-axis'
    )

    args = parser.parse_args()

    base_dir = Path(args.base_dir)

    # Discover experiment directories and derive display names
    print(f"Discovering experiments in {base_dir}...")
    experiment_dirs: Dict[str, Path] = {}
    display_names: Dict[str, str] = {}

    for strategy in args.strategies:
        experiment_dir = discover_experiment_for_strategy(base_dir, strategy, args.subfolder)
        experiment_dirs[strategy] = experiment_dir
        try:
            run_summary = load_run_summary(experiment_dir)
            display_names[strategy] = derive_experiment_name_from_summary(experiment_dir, run_summary)
        except FileNotFoundError:
            # Fallback to strategy name if run_summary.json not found
            display_names[strategy] = strategy
        print(f"  {strategy}: {experiment_dir.name} -> {display_names[strategy]}")

    print()

    # Extract proof lengths by calling extract_proof_lengths.py
    data = extract_proof_lengths(args.base_dir, args.strategies, args.subfolder)

    by_sorry_strategy = data['by_sorry_strategy']
    strategies = data['metadata']['strategies']

    print(f"\nStrategies: {[display_names.get(s, s) for s in strategies]}")

    # Find sorries solved by ALL strategies
    common_sorries = find_sorries_solved_by_all(by_sorry_strategy, strategies)
    print(f"Sorries solved by all {len(strategies)} strategies: {len(common_sorries)}")

    if len(common_sorries) == 0:
        print("Error: No sorries were solved by all strategies")
        sys.exit(1)

    # Collect lengths for common sorries
    lengths_by_strategy = collect_lengths_for_common_sorries(
        by_sorry_strategy, common_sorries, strategies
    )

    # Print summary statistics
    print_summary_stats(lengths_by_strategy, strategies, display_names)

    # Create box plot
    output_path = Path(args.output)
    create_box_plot(lengths_by_strategy, strategies, display_names, output_path, len(common_sorries), args.log_scale)


if __name__ == '__main__':
    main()
