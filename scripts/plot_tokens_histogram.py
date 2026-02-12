#!/usr/bin/env python3
"""
Plot histogram of tokens used to solve sorries across experiments.

Similar interface to compare_strategies.py - discovers experiments by strategy name
and subfolder, then generates a histogram showing token distribution for verified proofs.

Usage:
    python scripts/plot_tokens_histogram.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --strategies claude gemini goedel \
        --subfolder 1000

    # Or specify experiments directly:
    python scripts/plot_tokens_histogram.py \
        --experiments path/to/exp1 path/to/exp2
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


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

    # Find all subdirectories containing result.json
    experiment_dirs = [
        d for d in strategy_path.iterdir()
        if d.is_dir() and (d / "result.json").exists()
    ]

    if len(experiment_dirs) == 0:
        print(f"Error: No experiments found in {strategy_path}")
        print("(Looking for subdirectories containing result.json)")
        sys.exit(1)

    if len(experiment_dirs) > 1:
        # Sort by directory name (timestamp format YYYY-MM-DD_HH-MM-SS_*) and pick most recent
        experiment_dirs = sorted(experiment_dirs, key=lambda d: d.name)
        print(f"  Note: Multiple experiments found, using most recent: {experiment_dirs[-1].name}")
        return experiment_dirs[-1]

    return experiment_dirs[0]


def derive_experiment_name(folder_path: Path) -> str:
    """
    Derive experiment name from run_summary.json metadata.

    Uses the same naming logic as compare_experiments.py for consistency.

    Args:
        folder_path: Path to experiment folder

    Returns:
        Experiment name string
    """
    run_summary_path = folder_path / "run_summary.json"

    # Model name to display name mapping (same as compare_experiments.py)
    model_display_names = {
        "claude-opus-4-5": "Claude Opus 4.5",
        "gemini-3-flash-preview": "Gemini Flash 3",
        "gemini-3-pro-preview": "Gemini Pro 3",
        "qwen": "Qwen 3",
    }

    try:
        with open(run_summary_path, 'r') as f:
            run_summary = json.load(f)

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
                    provider_display_names = {
                        'goedel': 'Goedel Prover V2',
                        'qwen': 'Qwen 3',
                        'kimina': 'Kimina 8B',
                    }
                    return provider_display_names.get(provider, provider)
                except KeyError:
                    return folder_path.parent.name

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
                pass

        # For non-LLM strategies, return strategy name (with display name mapping)
        display_names = {
            'multi_tactic': 'Tactics',
            'goedel': 'Goedel Prover V2',
        }
        return display_names.get(strategy_name, strategy_name)

    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return folder_path.parent.name


# Custom colors for each model (same as compare_experiments.py)
CUSTOM_COLORS = {
    "Combined": "#333333",  # Dark Gray
    "Claude Opus 4.5 (SC)": "#1F77B4",  # Dark Blue
    "Claude Opus 4.5": "#AEC7E8",  # Light Blue
    "Gemini Flash 3 (SC)": "#006400",  # Dark Green
    "Gemini Flash 3 (agentic)": "#2CA02C",  # Green
    "Gemini Flash 3": "#98DF8A",  # Light Green
    "Gemini Pro 3": "#F4A3A3",  # Light Red
    "Goedel Prover V2": "#9467BD",  # Purple
    "Tactics": "#17BECF",  # Teal
    "Qwen 3": "#FFBB78",  # Soft Orange
    "Kimina 8B": "#C9A0DC",  # Light Purple
}

# Fallback color palette for unknown experiment names
FALLBACK_COLORS = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22', '#95a5a6']


def get_color_for_experiment(name: str, index: int) -> str:
    """Get the color for an experiment name, using custom colors if available."""
    if name in CUSTOM_COLORS:
        return CUSTOM_COLORS[name]
    return FALLBACK_COLORS[index % len(FALLBACK_COLORS)]


def load_token_data(result_json_path: Path) -> List[Dict]:
    """
    Load result.json and extract token data for verified proofs.

    Args:
        result_json_path: Path to result.json file

    Returns:
        List of dicts with token information for verified proofs
    """
    with open(result_json_path, 'r') as f:
        data = json.load(f)

    token_data = []
    for entry in data:
        if entry.get('proof_verified', False):
            input_tokens = entry.get('input_tokens', 0)
            output_tokens = entry.get('output_tokens', 0)
            total_tokens = input_tokens + output_tokens

            # Only include if we have token data
            if total_tokens > 0:
                token_data.append({
                    'sorry_id': entry.get('sorry', {}).get('id'),
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'total_tokens': total_tokens,
                })

    return token_data


def generate_histogram(
    experiments: List[Tuple[str, List[Dict]]],
    output_path: str,
    token_type: str = 'total',
    bins: int = 30,
    log_scale: bool = False,
):
    """
    Generate a histogram of token usage across experiments.

    Args:
        experiments: List of (experiment_name, token_data) tuples
        output_path: Path to save the chart
        token_type: Which tokens to plot ('input', 'output', or 'total')
        bins: Number of histogram bins
        log_scale: Whether to use log scale for x-axis
    """
    if not MATPLOTLIB_AVAILABLE:
        print("Warning: matplotlib not available. Install it or use: uv run --with matplotlib")
        return

    token_key = f'{token_type}_tokens'

    # Set font to match paper style
    plt.rcParams['font.family'] = 'serif'
    plt.rcParams['font.serif'] = ['Times New Roman']

    # Create figure
    fig, ax = plt.subplots(figsize=(12, 6))

    # Collect all token values to determine bin range
    all_tokens = []
    for _, token_data in experiments:
        all_tokens.extend([d[token_key] for d in token_data if d[token_key] > 0])

    if not all_tokens:
        print("Warning: No token data found for any verified proofs")
        return

    import numpy as np

    # Determine shared bin edges for all experiments (ensures equal bar widths)
    min_val = min(all_tokens)
    max_val = max(all_tokens)

    if log_scale:
        min_val = max(1, min_val)
        bin_edges = np.logspace(np.log10(min_val), np.log10(max_val), bins + 1)
    else:
        bin_edges = np.linspace(0, max_val, bins + 1)

    # Plot histogram for each experiment
    for i, (name, token_data) in enumerate(experiments):
        tokens = [d[token_key] for d in token_data if d[token_key] > 0]
        if tokens:
            ax.hist(
                tokens,
                bins=bin_edges,
                alpha=0.6,
                label=f"{name} (n={len(tokens)})",
                color=get_color_for_experiment(name, i),
                edgecolor='white',
                linewidth=0.5,
            )

    # Customize chart
    token_type_display = {
        'input': 'Input Tokens',
        'output': 'Output Tokens',
        'total': 'Total Tokens'
    }
    ax.set_xlabel(token_type_display[token_type], fontsize=14)
    ax.set_ylabel('Number of Verified Proofs', fontsize=14)

    if log_scale:
        ax.set_xscale('log')

    ax.legend(fontsize=11)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Adjust layout
    plt.tight_layout()

    # Save figure
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"✓ Histogram written to {output_path}")


def generate_boxplot(
    experiments: List[Tuple[str, List[Dict]]],
    output_path: str,
    token_type: str = 'total',
    log_scale: bool = False,
):
    """
    Generate a box plot of token usage across experiments.

    Args:
        experiments: List of (experiment_name, token_data) tuples
        output_path: Path to save the chart
        token_type: Which tokens to plot ('input', 'output', or 'total')
        log_scale: Whether to use log scale for y-axis
    """
    if not MATPLOTLIB_AVAILABLE:
        print("Warning: matplotlib not available. Install it or use: uv run --with matplotlib")
        return

    token_key = f'{token_type}_tokens'

    # Set font to match paper style
    plt.rcParams['font.family'] = 'serif'
    plt.rcParams['font.serif'] = ['Times New Roman']

    # Create figure
    fig, ax = plt.subplots(figsize=(10, 6))

    # Prepare data for boxplot
    data = []
    labels = []
    experiment_names = []  # Track names for color mapping
    for idx, (name, token_data) in enumerate(experiments):
        tokens = [d[token_key] for d in token_data if d[token_key] > 0]
        if tokens:
            data.append(tokens)
            labels.append(f"{name}\n(n={len(tokens)})")
            experiment_names.append((name, idx))

    if not data:
        print("Warning: No token data found for any verified proofs")
        return

    # Create boxplot
    bp = ax.boxplot(data, tick_labels=labels, patch_artist=True)

    # Apply custom colors to boxes
    for i, patch in enumerate(bp['boxes']):
        name, orig_idx = experiment_names[i]
        patch.set_facecolor(get_color_for_experiment(name, orig_idx))
        patch.set_alpha(0.7)

    # Customize chart
    token_type_display = {
        'input': 'Input Tokens',
        'output': 'Output Tokens',
        'total': 'Total Tokens'
    }
    ax.set_ylabel(token_type_display[token_type], fontsize=14)

    if log_scale:
        ax.set_yscale('log')

    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(axis='x', labelsize=11)
    ax.tick_params(axis='y', labelsize=12)

    # Adjust layout
    plt.tight_layout()

    # Save figure
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"✓ Boxplot written to {output_path}")


def print_statistics(experiments: List[Tuple[str, List[Dict]]], token_type: str = 'total'):
    """Print summary statistics for each experiment."""
    token_key = f'{token_type}_tokens'

    print("\n" + "=" * 80)
    print(f"TOKEN STATISTICS ({token_type.upper()})")
    print("=" * 80)

    for name, token_data in experiments:
        tokens = [d[token_key] for d in token_data if d[token_key] > 0]
        if tokens:
            import statistics
            print(f"\n{name}:")
            print(f"  Count:  {len(tokens)} verified proofs with token data")
            print(f"  Min:    {min(tokens):,}")
            print(f"  Max:    {max(tokens):,}")
            print(f"  Mean:   {statistics.mean(tokens):,.1f}")
            print(f"  Median: {statistics.median(tokens):,.1f}")
            if len(tokens) > 1:
                print(f"  StdDev: {statistics.stdev(tokens):,.1f}")
            print(f"  Total:  {sum(tokens):,}")
        else:
            print(f"\n{name}: No token data available")

    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description='Generate histogram of tokens used to solve sorries across experiments'
    )

    # Strategy-based discovery (like compare_strategies.py)
    parser.add_argument(
        '--base-dir',
        help='Base directory containing strategy folders'
    )
    parser.add_argument(
        '--strategies',
        nargs='+',
        help='List of strategy names to compare'
    )
    parser.add_argument(
        '--subfolder',
        help='Subfolder within each strategy (e.g., "1000")'
    )

    # Or direct experiment paths
    parser.add_argument(
        '--experiments',
        nargs='+',
        help='Direct paths to experiment folders (alternative to --base-dir/--strategies/--subfolder)'
    )

    # Output options
    parser.add_argument(
        '--output',
        default='charts/tokens_histogram.pdf',
        help='Path for histogram output file (default: charts/tokens_histogram.pdf)'
    )
    parser.add_argument(
        '--output-boxplot',
        help='Path for boxplot output file (optional)'
    )
    parser.add_argument(
        '--token-type',
        choices=['input', 'output', 'total'],
        default='total',
        help='Which tokens to plot (default: total)'
    )
    parser.add_argument(
        '--bins',
        type=int,
        default=50,
        help='Number of histogram bins (default: 50)'
    )
    parser.add_argument(
        '--log-scale',
        action='store_true',
        help='Use logarithmic scale for x-axis'
    )
    parser.add_argument(
        '--no-stats',
        action='store_true',
        help='Skip printing statistics'
    )

    args = parser.parse_args()

    # Determine experiment directories
    experiment_dirs: List[Path] = []
    strategy_names: List[str] = []

    if args.experiments:
        # Direct paths provided
        for exp_path in args.experiments:
            exp_path = Path(exp_path)
            if not exp_path.exists():
                print(f"Error: Experiment path does not exist: {exp_path}")
                sys.exit(1)
            experiment_dirs.append(exp_path)
            strategy_names.append(exp_path.parent.name)
    elif args.base_dir and args.strategies and args.subfolder:
        # Strategy-based discovery
        base_dir = Path(args.base_dir)
        if not base_dir.exists():
            print(f"Error: Base directory does not exist: {base_dir}")
            sys.exit(1)

        print(f"Discovering experiments in {base_dir}...")
        for strategy in args.strategies:
            experiment_dir = discover_experiment_for_strategy(base_dir, strategy, args.subfolder)
            print(f"  {strategy}: {experiment_dir.name}")
            experiment_dirs.append(experiment_dir)
            strategy_names.append(strategy)
        print()
    else:
        print("Error: Must provide either --experiments OR (--base-dir, --strategies, --subfolder)")
        sys.exit(1)

    # Load token data for each experiment
    experiments: List[Tuple[str, List[Dict]]] = []
    for exp_dir, strategy in zip(experiment_dirs, strategy_names):
        result_json = exp_dir / "result.json"
        if not result_json.exists():
            print(f"Warning: No result.json found in {exp_dir}")
            continue

        name = derive_experiment_name(exp_dir)
        token_data = load_token_data(result_json)
        experiments.append((name, token_data))
        print(f"✓ Loaded {len(token_data)} verified proofs with token data from {name}")

    if not experiments:
        print("Error: No experiments with token data found")
        sys.exit(1)

    # Print statistics
    if not args.no_stats:
        print_statistics(experiments, args.token_type)

    # Ensure output directory exists
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    # Generate histogram
    generate_histogram(
        experiments,
        args.output,
        token_type=args.token_type,
        bins=args.bins,
        log_scale=args.log_scale,
    )

    # Generate boxplot if requested
    if args.output_boxplot:
        Path(args.output_boxplot).parent.mkdir(parents=True, exist_ok=True)
        generate_boxplot(
            experiments,
            args.output_boxplot,
            token_type=args.token_type,
            log_scale=args.log_scale,
        )

    print("\n✓ Done!")


if __name__ == '__main__':
    main()
