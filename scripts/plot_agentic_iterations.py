#!/usr/bin/env python3
"""
Plot cumulative sorries solved by iteration for agentic strategies.

Discovers experiments by strategy name and subfolder, loads agentic_iterations.json,
and plots how many sorries are solved at each iteration.

Usage:
    python scripts/plot_agentic_iterations.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --strategies agentic gemini_agentic \
        --subfolder 1000 \
        --output agentic_iterations_plot.png
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt


def derive_experiment_name_from_summary(folder_path: Path, run_summary: Dict[str, Any]) -> str:
    """
    Derive experiment name from run_summary.json metadata.
    (Same logic as compare_experiments.py)

    For agentic strategies, returns model name with "(self-correction)" suffix.
    """
    try:
        strategy_name = run_summary['strategy']['name']

        # For agentic strategies, use the model name
        if strategy_name == 'agentic':
            try:
                model = run_summary['strategy']['args']['model']
                # Clean up model name (e.g., "google_genai:gemini-3-flash-preview" -> "gemini-3-flash-preview")
                if ':' in model:
                    model = model.split(':')[-1]
                return f"{model} (self-correction)"
            except KeyError:
                pass  # Fall through to return just "agentic"

        # Fallback to strategy name
        return strategy_name

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
        strategy: Strategy name (e.g., 'agentic', 'gemini_agentic')
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

    # Find all subdirectories containing agentic_iterations.json
    experiment_dirs = [
        d for d in strategy_path.iterdir()
        if d.is_dir() and (d / "agentic_iterations.json").exists()
    ]

    if len(experiment_dirs) == 0:
        print(f"Error: No experiments found in {strategy_path}")
        print("(Looking for subdirectories containing agentic_iterations.json)")
        print("Run extract_agentic_iterations.py first to generate the data.")
        sys.exit(1)

    if len(experiment_dirs) > 1:
        # Sort by directory name (timestamp format YYYY-MM-DD_HH-MM-SS_*) and pick most recent
        experiment_dirs = sorted(experiment_dirs, key=lambda d: d.name)
        print(f"  Note: Multiple experiments found, using most recent: {experiment_dirs[-1].name}")
        return experiment_dirs[-1]

    return experiment_dirs[0]


def load_agentic_iterations(experiment_dir: Path) -> Dict:
    """Load agentic_iterations.json from experiment directory."""
    results_path = experiment_dir / "agentic_iterations.json"
    if not results_path.exists():
        raise FileNotFoundError(f"agentic_iterations.json not found in {experiment_dir}")

    with open(results_path) as f:
        return json.load(f)


def compute_cumulative_solved(results: Dict[str, Optional[int]], max_iterations: int) -> List[int]:
    """
    Compute cumulative count of sorries solved at each iteration.

    Args:
        results: Dict mapping sorry_id -> iteration number (or null)
        max_iterations: Maximum number of iterations

    Returns:
        List of length max_iterations where entry i is the count of sorries
        solved using iterations 1..i+1
    """
    cumulative = []

    for i in range(1, max_iterations + 1):
        # Count sorries solved at iteration <= i
        count = sum(1 for v in results.values() if v is not None and v <= i)
        cumulative.append(count)

    return cumulative


def main():
    parser = argparse.ArgumentParser(
        description='Plot cumulative sorries solved by iteration for agentic strategies'
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
        type=Path,
        default=Path('agentic_iterations_plot.png'),
        help='Output file path for the plot (default: agentic_iterations_plot.png)'
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

    # Load iteration results and compute cumulative curves
    curves = []
    labels = []
    max_iterations_value = None

    for strategy, exp_dir in zip(args.strategies, experiment_dirs):
        try:
            data = load_agentic_iterations(exp_dir)
        except FileNotFoundError as e:
            print(f"Error: {e}")
            print("Run extract_agentic_iterations.py first to generate the data.")
            sys.exit(1)

        # Derive label from run_summary.json
        try:
            run_summary = load_run_summary(exp_dir)
            label = derive_experiment_name_from_summary(exp_dir, run_summary)
        except FileNotFoundError:
            label = strategy  # Fallback to strategy name

        if max_iterations_value is None:
            max_iterations_value = data["max_iterations"]
        elif data["max_iterations"] != max_iterations_value:
            print(f"Warning: {strategy} has max_iterations={data['max_iterations']}, expected {max_iterations_value}")

        cumulative = compute_cumulative_solved(data["results"], data["max_iterations"])
        curves.append(cumulative)
        labels.append(label)
        print(f"  {label}: {cumulative[-1]} sorries solved at iteration {data['max_iterations']}")

    # Override with custom labels if provided
    if args.labels:
        labels = args.labels

    print()

    # Set font to match paper style
    plt.rcParams['font.family'] = 'serif'
    plt.rcParams['font.serif'] = ['Times New Roman']

    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))

    x = list(range(1, max_iterations_value + 1))

    # Custom colors for each model (matching compare_experiments.py)
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
    # Fallback color
    fallback_color = '#95a5a6'

    for i, (label, curve) in enumerate(zip(labels, curves)):
        color = custom_colors.get(label, fallback_color)
        ax.plot(x, curve, marker='o', markersize=3, label=label,
                color=color, linewidth=2)

    ax.set_xlabel('Iteration', fontsize=20)
    ax.set_ylabel('Sorries Solved', fontsize=20)
    if args.title:
        ax.set_title(args.title, fontsize=14, fontweight='bold')

    # Legend at top, centered, no frame
    ax.legend(bbox_to_anchor=(0.5, 1.20), loc='upper center', ncol=2, frameon=False, fontsize=18)

    ax.grid(axis='y', alpha=0.3, linestyle='--')

    # Remove top and right spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Tick label sizes (matching compare_experiments.py category charts)
    ax.tick_params(axis='x', labelsize=18)
    ax.tick_params(axis='y', labelsize=16)

    # Set x-axis to show integer ticks
    ax.set_xticks(range(1, max_iterations_value + 1, max(1, max_iterations_value // 10)))

    plt.tight_layout(pad=0)
    plt.savefig(args.output, dpi=150, bbox_inches='tight', pad_inches=0)
    print(f"Plot saved to: {args.output}")


if __name__ == '__main__':
    main()
