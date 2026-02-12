#!/usr/bin/env python3
"""
Plot cumulative sorries solved by # of LLM calls for both pass@k and agentic strategies.

Combines data from:
- pass_at_k_results.json (for pass@k strategies like claude, gemini, goedel)
- agentic_iterations.json (for agentic strategies)

Usage:
    python scripts/plot_combined_llm_calls.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --pass-at-k-strategies gemini claude goedel \
        --agentic-strategies agentic gemini_agentic \
        --subfolder 1000 \
        --output charts/combined_llm_calls.png
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt


def derive_experiment_name_from_summary(
    folder_path: Path, run_summary: Dict[str, Any]
) -> str:
    """
    Derive experiment name from run_summary.json metadata.
    (Same logic as compare_experiments.py)
    """
    model_display_names = {
        "claude-opus-4-5": "Claude Opus 4.5",
        "gemini-3-flash-preview": "Gemini Flash 3",
        "gemini-3-pro-preview": "Gemini Pro 3",
        "qwen": "Qwen 3",
        "gpt-5.2": "GPT 5.2",
    }

    try:
        strategy_name = run_summary["strategy"]["name"]

        # For LLM strategies, use the model name or provider name
        if strategy_name == "llm":
            try:
                model = run_summary["strategy"]["args"]["model_config"]["params"][
                    "model"
                ]
                return model_display_names.get(model, model)
            except KeyError:
                try:
                    provider = run_summary["strategy"]["args"]["model_config"][
                        "provider"
                    ]
                    provider_display_names = {
                        "goedel": "Goedel Prover V2",
                        "qwen": "Qwen 3",
                        "kimina": "Kimina 8B",
                        "gpt": "GPT 5.2",
                    }
                    return provider_display_names.get(provider, provider)
                except KeyError:
                    parent_dir = folder_path.parent.name
                    return parent_dir

        # For agentic strategies, append the model name
        if strategy_name == "agentic":
            try:
                model = run_summary["strategy"]["args"]["model"]
                if ":" in model:
                    model = model.split(":")[-1]
                base_name = model_display_names.get(model, model)
                enable_tools = run_summary["strategy"]["args"].get(
                    "enable_tools", False
                )
                if enable_tools:
                    return f"{base_name} (agentic)"
                return f"{base_name} (SC)"
            except KeyError:
                pass

        display_names = {
            "multi_tactic": "Tactics",
            "goedel": "Goedel Prover V2",
        }
        return display_names.get(strategy_name, strategy_name)

    except KeyError as e:
        print(f"Error: Missing key {e} in run_summary.json for {folder_path}")
        return folder_path.name


def load_run_summary(experiment_dir: Path) -> Dict[str, Any]:
    """Load run_summary.json from experiment directory."""
    run_summary_path = experiment_dir / "run_summary.json"
    if not run_summary_path.exists():
        raise FileNotFoundError(f"run_summary.json not found in {experiment_dir}")

    with open(run_summary_path) as f:
        return json.load(f)


def discover_experiment_for_pass_at_k(
    base_dir: Path, strategy: str, subfolder: str
) -> Path:
    """Discover experiment directory for pass@k strategy (looks for analysis.json)."""
    strategy_path = base_dir / strategy / subfolder

    if not strategy_path.exists():
        print(f"Error: Strategy path does not exist: {strategy_path}")
        sys.exit(1)

    experiment_dirs = [
        d
        for d in strategy_path.iterdir()
        if d.is_dir() and (d / "analysis.json").exists()
    ]

    if len(experiment_dirs) == 0:
        print(f"Error: No experiments found in {strategy_path}")
        sys.exit(1)

    if len(experiment_dirs) > 1:
        experiment_dirs = sorted(experiment_dirs, key=lambda d: d.name)
        print(
            f"  Note: Multiple experiments found, using most recent: {experiment_dirs[-1].name}"
        )
        return experiment_dirs[-1]

    return experiment_dirs[0]


def discover_experiment_for_agentic(
    base_dir: Path, strategy: str, subfolder: str
) -> Path:
    """Discover experiment directory for agentic strategy (looks for agentic_iterations.json)."""
    strategy_path = base_dir / strategy / subfolder

    if not strategy_path.exists():
        print(f"Error: Strategy path does not exist: {strategy_path}")
        sys.exit(1)

    experiment_dirs = [
        d
        for d in strategy_path.iterdir()
        if d.is_dir() and (d / "agentic_iterations.json").exists()
    ]

    if len(experiment_dirs) == 0:
        print(f"Error: No experiments found in {strategy_path}")
        print("Run extract_agentic_iterations.py first to generate the data.")
        sys.exit(1)

    if len(experiment_dirs) > 1:
        experiment_dirs = sorted(experiment_dirs, key=lambda d: d.name)
        print(
            f"  Note: Multiple experiments found, using most recent: {experiment_dirs[-1].name}"
        )
        return experiment_dirs[-1]

    return experiment_dirs[0]


def load_pass_at_k_results(experiment_dir: Path) -> Dict:
    """
    Load pass_at_k_results.json from experiment directory, merging with reruns.

    Merge order: main -> oldest rerun -> ... -> most recent rerun
    Later reruns take precedence by sorry ID.
    """
    results_path = experiment_dir / "pass_at_k_results.json"
    if not results_path.exists():
        raise FileNotFoundError(f"pass_at_k_results.json not found in {experiment_dir}")

    with open(results_path) as f:
        main_data = json.load(f)

    # Start with main results
    merged_results = dict(main_data["results"])
    k_value = main_data["k"]

    # Check for reruns
    rerun_dir = experiment_dir / "rerun"
    if rerun_dir.exists():
        rerun_subdirs = [
            d
            for d in rerun_dir.iterdir()
            if d.is_dir() and (d / "pass_at_k_results.json").exists()
        ]

        if rerun_subdirs:
            # Sort by timestamp (oldest first, most recent last)
            rerun_subdirs = sorted(rerun_subdirs, key=lambda d: d.name)

            for rerun_subdir in rerun_subdirs:
                rerun_path = rerun_subdir / "pass_at_k_results.json"
                with open(rerun_path) as f:
                    rerun_data = json.load(f)
                # Merge: rerun overwrites main for same sorry_id
                merged_results.update(rerun_data["results"])

    return {"k": k_value, "results": merged_results}


def load_agentic_iterations(experiment_dir: Path) -> Dict:
    """
    Load agentic_iterations.json from experiment directory, merging with reruns.

    Merge order: main -> oldest rerun -> ... -> most recent rerun
    Later reruns take precedence by sorry ID.
    """
    results_path = experiment_dir / "agentic_iterations.json"
    if not results_path.exists():
        raise FileNotFoundError(
            f"agentic_iterations.json not found in {experiment_dir}"
        )

    with open(results_path) as f:
        main_data = json.load(f)

    # Start with main results
    merged_results = dict(main_data["results"])
    max_iterations = main_data["max_iterations"]

    # Check for reruns
    rerun_dir = experiment_dir / "rerun"
    if rerun_dir.exists():
        rerun_subdirs = [
            d
            for d in rerun_dir.iterdir()
            if d.is_dir() and (d / "agentic_iterations.json").exists()
        ]

        if rerun_subdirs:
            # Sort by timestamp (oldest first, most recent last)
            rerun_subdirs = sorted(rerun_subdirs, key=lambda d: d.name)

            for rerun_subdir in rerun_subdirs:
                rerun_path = rerun_subdir / "agentic_iterations.json"
                with open(rerun_path) as f:
                    rerun_data = json.load(f)
                # Merge: rerun overwrites main for same sorry_id
                merged_results.update(rerun_data["results"])

    return {"max_iterations": max_iterations, "results": merged_results}


def compute_cumulative_solved_pass_at_k(
    results: Dict[str, List[int]], k: int
) -> List[int]:
    """
    Compute cumulative count of sorries solved at each k for pass@k data.

    Args:
        results: Dict mapping sorry_id -> array of 0/1 for each attempt
        k: Total number of attempts

    Returns:
        List of length k where entry i is the count of sorries solved
        using attempts 1..i+1
    """
    cumulative = []

    for i in range(k):
        count = 0
        for arr in results.values():
            if any(arr[: i + 1]):
                count += 1
        cumulative.append(count)

    return cumulative


def compute_cumulative_solved_agentic(
    results: Dict[str, Optional[int]], max_iterations: int
) -> List[int]:
    """
    Compute cumulative count of sorries solved at each iteration for agentic data.

    Args:
        results: Dict mapping sorry_id -> iteration number (or null)
        max_iterations: Maximum number of iterations

    Returns:
        List of length max_iterations where entry i is the count of sorries
        solved using iterations 1..i+1
    """
    cumulative = []

    for i in range(1, max_iterations + 1):
        count = sum(1 for v in results.values() if v is not None and v <= i)
        cumulative.append(count)

    return cumulative


def main():
    parser = argparse.ArgumentParser(
        description="Plot cumulative sorries solved by # of LLM calls"
    )
    parser.add_argument(
        "--base-dir", required=True, help="Base directory containing strategy folders"
    )
    parser.add_argument(
        "--pass-at-k-strategies",
        nargs="+",
        default=[],
        help="List of pass@k strategy names (e.g., claude gemini goedel)",
    )
    parser.add_argument(
        "--agentic-strategies",
        nargs="+",
        default=[],
        help="List of agentic strategy names (e.g., agentic gemini_agentic)",
    )
    parser.add_argument(
        "--subfolder",
        required=True,
        help='Subfolder within each strategy (e.g., "1000")',
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("combined_llm_calls.png"),
        help="Output file path for the plot",
    )
    parser.add_argument("--title", default=None, help="Plot title (optional)")

    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        print(f"Error: Base directory does not exist: {base_dir}")
        sys.exit(1)

    if not args.pass_at_k_strategies and not args.agentic_strategies:
        print(
            "Error: Must specify at least one strategy via --pass-at-k-strategies or --agentic-strategies"
        )
        sys.exit(1)

    curves = []
    labels = []
    max_x = 0

    # Process pass@k strategies
    if args.pass_at_k_strategies:
        print(f"Discovering pass@k experiments in {base_dir}...")
        for strategy in args.pass_at_k_strategies:
            exp_dir = discover_experiment_for_pass_at_k(
                base_dir, strategy, args.subfolder
            )
            print(f"  {strategy}: {exp_dir.name}")

            try:
                data = load_pass_at_k_results(exp_dir)
            except FileNotFoundError as e:
                print(f"Error: {e}")
                print("Run extract_pass_at_k.py first to generate the data.")
                sys.exit(1)

            try:
                run_summary = load_run_summary(exp_dir)
                label = derive_experiment_name_from_summary(exp_dir, run_summary)
            except FileNotFoundError:
                label = strategy

            k = data["k"]
            cumulative = compute_cumulative_solved_pass_at_k(data["results"], k)
            curves.append(cumulative)
            labels.append(label)
            max_x = max(max_x, k)
            print(f"    {label}: {cumulative[-1]} sorries solved at k={k}")

    # Process agentic strategies
    if args.agentic_strategies:
        print(f"Discovering agentic experiments in {base_dir}...")
        for strategy in args.agentic_strategies:
            exp_dir = discover_experiment_for_agentic(
                base_dir, strategy, args.subfolder
            )
            print(f"  {strategy}: {exp_dir.name}")

            try:
                data = load_agentic_iterations(exp_dir)
            except FileNotFoundError as e:
                print(f"Error: {e}")
                print("Run extract_agentic_iterations.py first to generate the data.")
                sys.exit(1)

            try:
                run_summary = load_run_summary(exp_dir)
                label = derive_experiment_name_from_summary(exp_dir, run_summary)
            except FileNotFoundError:
                label = strategy

            max_iterations = data["max_iterations"]
            cumulative = compute_cumulative_solved_agentic(
                data["results"], max_iterations
            )
            curves.append(cumulative)
            labels.append(label)
            max_x = max(max_x, max_iterations)
            print(
                f"    {label}: {cumulative[-1]} sorries solved at iteration={max_iterations}"
            )

    print()

    # Set font to match paper style
    plt.rcParams["font.family"] = "serif"
    plt.rcParams["font.serif"] = ["Times New Roman"]

    # Plot - larger height to accommodate legend
    fig, ax = plt.subplots(figsize=(12, 10))

    # Custom colors for each model (matching compare_experiments.py)
    custom_colors = {
        "Combined": "#333333",  # Dark Gray
        "Claude Opus 4.5 (SC)": "#1F77B4",  # Dark Blue
        "Claude Opus 4.5": "#AEC7E8",  # Light Blue
        "Gemini Flash 3 (SC)": "#006400",  # Dark Green
        "Gemini Flash 3 (agentic)": "#2CA02C",  # Green
        "Gemini Flash 3": "#98DF8A",  # Light Green
        "Gemini Pro 3": "#F4A3A3",  # Light Red
        "GPT 5.2": "#FFEB99",  # Light Yellow
        "Goedel Prover V2": "#9467BD",  # Purple
        "Tactics": "#17BECF",  # Teal
        "Qwen 3": "#FFBB78",  # Soft Orange
        "Kimina 8B": "#C9A0DC",  # Light Purple
    }
    fallback_color = "#95a5a6"

    for label, curve in zip(labels, curves):
        x = list(range(1, len(curve) + 1))
        color = custom_colors.get(label, fallback_color)
        ax.plot(
            x, curve, marker="o", markersize=3, label=label, color=color, linewidth=2
        )

    ax.set_xlabel("Sample Proofs", fontsize=28)
    ax.set_ylabel("Sorries Solved", fontsize=28)
    if args.title:
        ax.set_title(args.title, fontsize=14, fontweight="bold")

    # Legend above plot area, centered, no frame
    handles, legend_labels = ax.get_legend_handles_labels()
    legend_cols = 2

    # Reorder legend entries so Gemini items are in the right column
    # Matplotlib fills legends row by row, so odd indices end up in right column
    gemini_items = [
        (h, l) for h, l in zip(handles, legend_labels) if "Gemini" in l
    ]
    other_items = [
        (h, l) for h, l in zip(handles, legend_labels) if "Gemini" not in l
    ]

    # Interleave: other items in left column (even indices), Gemini in right (odd indices)
    reordered = []
    max_len = max(len(other_items), len(gemini_items))
    for i in range(max_len):
        if i < len(other_items):
            reordered.append(other_items[i])
        if i < len(gemini_items):
            reordered.append(gemini_items[i])

    if reordered:
        handles, legend_labels = zip(*reordered)

    ax.legend(
        handles,
        legend_labels,
        bbox_to_anchor=(0.5, 1.02),
        loc="lower center",
        ncol=legend_cols,
        frameon=False,
        fontsize=24,
    )

    ax.grid(axis="y", alpha=0.3, linestyle="--")

    # Remove top and right spines
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Tick label sizes
    ax.tick_params(axis="x", labelsize=24)
    ax.tick_params(axis="y", labelsize=24)

    # Set x-axis to show integer ticks
    ax.set_xticks(range(1, max_x + 1, max(1, max_x // 10)))

    plt.tight_layout(rect=[0, 0, 1, 0.92], pad=0)
    plt.savefig(args.output, dpi=150, bbox_inches="tight", pad_inches=0)
    print(f"Plot saved to: {args.output}")


if __name__ == "__main__":
    main()
