#!/usr/bin/env python3
"""
Plot cumulative pass@k curves for multiple strategies.

Discovers experiments by strategy name and subfolder, loads pass_at_k_results.json,
and plots how many sorries are solved at each k value.

Usage:
    python scripts/plot_pass_at_k.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --strategies claude gemini gpt \
        --subfolder 1000 \
        --output pass_at_k_plot.png
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import matplotlib.pyplot as plt


def derive_experiment_name_from_summary(folder_path: Path, run_summary: Dict[str, Any]) -> str:
    """
    Derive experiment name from run_summary.json metadata.
    (Same logic as compare_experiments.py)

    For non-LLM strategies: Returns strategy name (e.g., 'rfl', 'supersimple')
    For LLM strategies: Returns model name (e.g., 'Gemini Flash 3', 'Claude Opus 4.5')
    """
    # Model name to display name mapping (matching compare_experiments.py)
    model_display_names = {
        "claude-opus-4-5": "Claude Opus 4.5",
        "gemini-3-flash-preview": "Gemini Flash 3",
        "gemini-3-pro-preview": "Gemini Pro 3",
        "qwen": "Qwen 3",
    }

    try:
        strategy_name = run_summary['strategy']['name']

        # For LLM strategies, use the model name or provider name
        if strategy_name == 'llm':
            try:
                # First try to get the model name
                model = run_summary['strategy']['args']['model_config']['params']['model']
                return model_display_names.get(model, model)
            except KeyError:
                # Fallback: try to get the provider name (for goedel, deepseek, etc.)
                try:
                    provider = run_summary['strategy']['args']['model_config']['provider']
                    # Map provider names to display names
                    provider_display_names = {
                        'goedel': 'Goedel Prover V2',
                        'qwen': 'Qwen 3',
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
                # Map to display name
                base_name = model_display_names.get(model, model)
                # Check if tools are enabled
                enable_tools = run_summary['strategy']['args'].get('enable_tools', False)
                if enable_tools:
                    return f"{base_name} (agentic)"
                return f"{base_name} (SC)"
            except KeyError:
                pass  # Fall through to return just "agentic"

        # For non-LLM strategies, return strategy name (with display name mapping)
        display_names = {
            'multi_tactic': 'Tactics',
            'goedel': 'Goedel Prover V2',
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


def compute_cumulative_solved(results: Dict[str, List[int]], k: int) -> List[int]:
    """
    Compute cumulative count of sorries solved at each k.

    Args:
        results: Dict mapping sorry_id -> array of 0/1 for each attempt
        k: Total number of attempts

    Returns:
        List of length k where entry i is the count of sorries solved
        using attempts 1..i+1
    """
    cumulative = []

    for i in range(k):
        # Count sorries that have at least one success in attempts 0..i (inclusive)
        count = 0
        for arr in results.values():
            if any(arr[:i + 1]):
                count += 1
        cumulative.append(count)

    return cumulative


def main():
    parser = argparse.ArgumentParser(
        description='Plot cumulative pass@k curves for multiple strategies'
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
        default=Path('pass_at_k_plot.png'),
        help='Output file path for the plot (default: pass_at_k_plot.png)'
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

    # Load pass@k results and compute cumulative curves
    # Also derive labels from run_summary.json (same as compare_experiments.py)
    curves = []
    labels = []
    k_value = None

    for strategy, exp_dir in zip(args.strategies, experiment_dirs):
        try:
            data = load_pass_at_k_results(exp_dir)
        except FileNotFoundError as e:
            print(f"Error: {e}")
            print("Run extract_pass_at_k.py first to generate the data.")
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

        cumulative = compute_cumulative_solved(data["results"], data["k"])
        curves.append(cumulative)
        labels.append(label)
        print(f"  {label}: {cumulative[-1]} sorries solved at k={data['k']}")

    # Override with custom labels if provided
    if args.labels:
        labels = args.labels

    print()

    # Set font to match paper style
    plt.rcParams['font.family'] = 'serif'
    plt.rcParams['font.serif'] = ['Times New Roman']

    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))

    x = list(range(1, k_value + 1))

    # Custom colors for each model (matching compare_experiments.py)
    custom_colors = {
        "Combined": "#333333",  # Dark Gray
        "Claude Opus 4.5 (SC)": "#1F77B4",  # Dark Blue
        "Claude Opus 4.5": "#AEC7E8",  # Light Blue
        "Gemini Flash 3 (SC)": "#006400",  # Dark Green
        "Gemini Flash 3 (agentic)": "#2CA02C",  # Green
        "Gemini Flash 3": "#98DF8A",  # Light Green
        "Gemini Pro 3": "#F4A3A3",  # Light Red
        "Goedel Prover V2": "#9467BD",  # Purple
        "Tactics": "#17BECF",  # Teal
        "Qwen 3": "#FF7F0E",  # Orange
    }
    # Fallback color
    fallback_color = '#95a5a6'

    for i, (label, curve) in enumerate(zip(labels, curves)):
        color = custom_colors.get(label, fallback_color)
        ax.plot(x, curve, marker='o', markersize=3, label=label,
                color=color, linewidth=2)

    ax.set_xlabel('Number of Attempts (k)', fontsize=20)
    ax.set_ylabel('Sorries Solved', fontsize=20)
    if args.title:
        ax.set_title(args.title, fontsize=14, fontweight='bold')

    # Legend at top, centered, no frame (2 columns = 2 rows for 4 items)
    ax.legend(bbox_to_anchor=(0.5, 1.20), loc='upper center', ncol=2, frameon=False, fontsize=18)

    ax.grid(axis='y', alpha=0.3, linestyle='--')

    # Remove top and right spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Tick label sizes (matching compare_experiments.py category charts)
    ax.tick_params(axis='x', labelsize=18)
    ax.tick_params(axis='y', labelsize=16)

    # Set x-axis to show integer ticks
    ax.set_xticks(range(1, k_value + 1, max(1, k_value // 10)))

    plt.tight_layout(pad=0)
    plt.savefig(args.output, dpi=150, bbox_inches='tight', pad_inches=0)
    print(f"Plot saved to: {args.output}")


if __name__ == '__main__':
    main()
