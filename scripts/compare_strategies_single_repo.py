#!/usr/bin/env python3
"""
Single-repo strategy comparison script.

Analyzes all theorems proven by any strategy for a single repository,
outputting a comparison chart and a JSON file mapping each sorry to
the strategies that solved it.

Usage:
    uv run --with matplotlib python3 scripts/compare_strategies_single_repo.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --strategies gpt kimina agentic gemini multi_tactic claude \
        --subfolder 1000 \
        --repo HEPLean/PhysLean \
        --output-chart charts/physlean_comparison.pdf \
        --output-json physlean_sorries_by_strategy.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any

try:
    import matplotlib.pyplot as plt
    import matplotlib

    matplotlib.use("Agg")  # Use non-interactive backend
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


def load_merged_results(experiment_dir: Path) -> List[Dict[str, Any]]:
    """
    Load result.json, merging with all reruns in timestamp order.
    Later reruns take precedence by sorry ID.

    Args:
        experiment_dir: Path to experiment directory containing result.json

    Returns:
        List of merged result entries
    """
    main_result = experiment_dir / "result.json"
    with open(main_result, 'r') as f:
        main_data = json.load(f)

    # Start with main results indexed by sorry ID
    merged_by_id = {entry['sorry']['id']: entry for entry in main_data}

    # Check for reruns
    rerun_dir = experiment_dir / "rerun"
    if rerun_dir.exists():
        rerun_subdirs = [
            d for d in rerun_dir.iterdir()
            if d.is_dir() and (d / "result.json").exists()
        ]

        if rerun_subdirs:
            # Sort by timestamp (oldest first, most recent last)
            rerun_subdirs = sorted(rerun_subdirs, key=lambda d: d.name)

            for rerun_subdir in rerun_subdirs:
                rerun_result = rerun_subdir / "result.json"
                with open(rerun_result, 'r') as f:
                    rerun_data = json.load(f)
                for entry in rerun_data:
                    sorry_id = entry['sorry']['id']
                    merged_by_id[sorry_id] = entry

    return list(merged_by_id.values())


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

    experiment_dirs = [
        d for d in strategy_path.iterdir()
        if d.is_dir() and (d / "analysis.json").exists()
    ]

    if len(experiment_dirs) == 0:
        print(f"Error: No experiments found in {strategy_path}")
        sys.exit(1)

    if len(experiment_dirs) > 1:
        experiment_dirs = sorted(experiment_dirs, key=lambda d: d.name)
        print(f"  Note: Multiple experiments found, using most recent: {experiment_dirs[-1].name}")
        return experiment_dirs[-1]

    return experiment_dirs[0]


def extract_repo_name(repo_url: str) -> str:
    """Extract owner/repo from GitHub URL."""
    url = repo_url.rstrip('/').removesuffix('.git')
    if url.startswith('https://github.com/'):
        return url.replace('https://github.com/', '')
    if url.startswith('http://github.com/'):
        return url.replace('http://github.com/', '')
    return url


def derive_strategy_display_name(experiment_dir: Path) -> str:
    """
    Derive display name from run_summary.json metadata.
    """
    model_display_names = {
        "claude-opus-4-5": "Claude Opus 4.5",
        "gemini-3-flash-preview": "Gemini Flash 3",
        "gemini-3-pro-preview": "Gemini Pro 3",
        "qwen": "Qwen 3",
        "gpt-5.2": "GPT 5.2",
    }

    run_summary_path = experiment_dir / "run_summary.json"
    if not run_summary_path.exists():
        return experiment_dir.parent.parent.name  # Use strategy folder name

    try:
        with open(run_summary_path, 'r') as f:
            run_summary = json.load(f)

        strategy_name = run_summary["strategy"]["name"]

        if strategy_name == "llm":
            try:
                model = run_summary["strategy"]["args"]["model_config"]["params"]["model"]
                return model_display_names.get(model, model)
            except KeyError:
                try:
                    provider = run_summary["strategy"]["args"]["model_config"]["provider"]
                    provider_display_names = {
                        "goedel": "Goedel Prover V2",
                        "qwen": "Qwen 3",
                        "kimina": "Kimina 8B",
                        "gpt": "GPT 5.2",
                    }
                    return provider_display_names.get(provider, provider)
                except KeyError:
                    return experiment_dir.parent.parent.name

        if strategy_name == "agentic":
            try:
                model = run_summary["strategy"]["args"]["model"]
                if ":" in model:
                    model = model.split(":")[-1]
                base_name = model_display_names.get(model, model)
                enable_tools = run_summary["strategy"]["args"].get("enable_tools", False)
                if enable_tools:
                    return f"{base_name} (agentic)"
                return f"{base_name} (SC)"
            except KeyError:
                return "agentic"

        display_names = {
            "multi_tactic": "Tactics",
            "goedel": "Goedel Prover V2",
        }
        return display_names.get(strategy_name, strategy_name)

    except (KeyError, json.JSONDecodeError):
        return experiment_dir.parent.parent.name


def load_repo_sorries_by_strategy(
    experiment_dirs: List[Path],
    strategies: List[str],
    repo_name: str
) -> Dict[str, Dict[str, Any]]:
    """
    Load all sorries for a specific repo and track which strategies solved each.

    Args:
        experiment_dirs: List of experiment directory paths
        strategies: List of strategy names (same order as experiment_dirs)
        repo_name: Repository name in "owner/repo" format

    Returns:
        Dict[sorry_id, {
            "sorry": full sorry object,
            "solved_by": [list of strategy names],
            "proofs": {strategy_name: proof text}
        }]
    """
    all_sorries: Dict[str, Dict[str, Any]] = {}

    for strategy, exp_dir in zip(strategies, experiment_dirs):
        if not (exp_dir / "result.json").exists():
            continue

        results = load_merged_results(exp_dir)

        for entry in results:
            sorry = entry.get('sorry', {})
            sorry_repo_url = sorry.get('repo', {}).get('remote', '')
            sorry_repo_name = extract_repo_name(sorry_repo_url)

            # Skip if not our target repo
            if sorry_repo_name != repo_name:
                continue

            sorry_id = sorry.get('id')
            if not sorry_id:
                continue

            # Initialize sorry entry if not seen before
            if sorry_id not in all_sorries:
                all_sorries[sorry_id] = {
                    "sorry": sorry,
                    "solved_by": [],
                    "proofs": {}
                }

            # Record if this strategy solved it
            if entry.get('proof_verified', False):
                display_name = derive_strategy_display_name(exp_dir)
                if display_name not in all_sorries[sorry_id]["solved_by"]:
                    all_sorries[sorry_id]["solved_by"].append(display_name)
                    proof = entry.get('proof')
                    if proof:
                        all_sorries[sorry_id]["proofs"][display_name] = proof

    return all_sorries


def generate_single_repo_chart(
    sorries_data: Dict[str, Dict[str, Any]],
    strategies_summary: Dict[str, Dict[str, Any]],
    repo_name: str,
    combined_solved: int,
    total_sorries: int,
    output_path: str,
    show_percent: bool = False
):
    """
    Generate a bar chart comparing strategies for a single repo.
    """
    if not MATPLOTLIB_AVAILABLE:
        print("Warning: matplotlib not available. Install it or use: uv run --with matplotlib")
        return

    # Prepare data
    strategy_names = list(strategies_summary.keys())

    if show_percent:
        values = [strategies_summary[s]["rate"] for s in strategy_names]
        combined_value = (combined_solved / total_sorries * 100) if total_sorries > 0 else 0
    else:
        values = [strategies_summary[s]["solved"] for s in strategy_names]
        combined_value = combined_solved

    # Add combined bar
    strategy_names.append("Combined")
    values.append(combined_value)

    # Sort by value (excluding Combined)
    paired = list(zip(strategy_names[:-1], values[:-1]))
    paired.sort(key=lambda x: x[1], reverse=True)
    strategy_names = [p[0] for p in paired] + ["Combined"]
    values = [p[1] for p in paired] + [combined_value]

    # Create figure
    fig, ax = plt.subplots(figsize=(12, 6))

    # Color palette
    colors = [
        "#3498db", "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6",
        "#1abc9c", "#e67e22", "#95a5a6", "#34495e", "#16a085",
        "#c0392b", "#8e44ad"
    ]
    bar_colors = []
    for i, name in enumerate(strategy_names):
        if name == "Combined":
            bar_colors.append("#2c3e50")  # Dark gray for Combined
        else:
            bar_colors.append(colors[i % len(colors)])

    # Create bars
    x = range(len(strategy_names))
    bars = ax.bar(x, values, alpha=0.8, color=bar_colors)

    # Add value labels on bars
    for bar, val in zip(bars, values):
        height = bar.get_height()
        label = f"{val:.1f}%" if show_percent else f"{int(val)}"
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height,
            label,
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold"
        )

    # Customize chart
    ax.set_xlabel("Strategy", fontsize=12)
    if show_percent:
        ax.set_ylabel("Success Rate (%)", fontsize=12)
        ax.set_title(f"Strategy Success Rates for {repo_name} (n={total_sorries})", fontsize=14, fontweight="bold")
        ax.set_ylim(0, 105)
    else:
        ax.set_ylabel("Sorries Solved", fontsize=12)
        ax.set_title(f"Strategy Comparison for {repo_name}", fontsize=14, fontweight="bold")
        max_val = max(values) if values else 10
        if max_val == 0:
            max_val = 1  # Avoid singular transformation when all values are 0
        ax.set_ylim(0, max_val * 1.15)

    ax.set_xticks(x)
    ax.set_xticklabels(strategy_names, rotation=45, ha="right", fontsize=10)
    ax.grid(axis="y", alpha=0.3, linestyle="--")

    # Adjust layout
    plt.tight_layout()

    # Save figure
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Chart written to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Compare strategies for a single repository'
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
        help='List of strategy names to compare (minimum 2)'
    )
    parser.add_argument(
        '--subfolder',
        required=True,
        help='Subfolder within each strategy (e.g., "1000")'
    )
    parser.add_argument(
        '--repo',
        required=True,
        help='Repository name in "owner/repo" format (e.g., "HEPLean/PhysLean")'
    )
    parser.add_argument(
        '--output-chart',
        default='charts/repo_comparison.pdf',
        help='Path for output chart (default: charts/repo_comparison.pdf)'
    )
    parser.add_argument(
        '--output-json',
        default='repo_sorries_by_strategy.json',
        help='Path for JSON output (default: repo_sorries_by_strategy.json)'
    )
    parser.add_argument(
        '--percent',
        action='store_true',
        help='Show success rate percentages instead of absolute counts in chart'
    )

    args = parser.parse_args()

    # Validate minimum strategies
    if len(args.strategies) < 2:
        print(f"Error: Need at least 2 strategies to compare, got {len(args.strategies)}")
        sys.exit(1)

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        print(f"Error: Base directory does not exist: {base_dir}")
        sys.exit(1)

    # Discover experiment directories
    print(f"Discovering experiments in {base_dir}...")
    experiment_dirs: List[Path] = []

    for strategy in args.strategies:
        experiment_dir = discover_experiment_for_strategy(base_dir, strategy, args.subfolder)
        print(f"  {strategy}: {experiment_dir.name}")
        experiment_dirs.append(experiment_dir)

    print()

    # Load sorries for the target repo
    print(f"Loading sorries for {args.repo}...")
    sorries_data = load_repo_sorries_by_strategy(
        experiment_dirs, args.strategies, args.repo
    )

    total_sorries = len(sorries_data)
    combined_solved = sum(1 for s in sorries_data.values() if s["solved_by"])

    print(f"  Total sorries in {args.repo}: {total_sorries}")
    print(f"  Sorries solved by at least one strategy: {combined_solved}")
    print()

    # Compute per-strategy statistics
    strategies_summary: Dict[str, Dict[str, Any]] = {}

    for exp_dir in experiment_dirs:
        display_name = derive_strategy_display_name(exp_dir)
        solved = sum(1 for s in sorries_data.values() if display_name in s["solved_by"])
        rate = (solved / total_sorries * 100) if total_sorries > 0 else 0.0
        strategies_summary[display_name] = {
            "solved": solved,
            "rate": round(rate, 2)
        }

    # Print summary
    print("=" * 60)
    print(f"STRATEGY COMPARISON FOR {args.repo}")
    print("=" * 60)
    for name, stats in sorted(strategies_summary.items(), key=lambda x: x[1]["solved"], reverse=True):
        print(f"  {name}: {stats['solved']}/{total_sorries} ({stats['rate']}%)")
    print(f"  Combined: {combined_solved}/{total_sorries} ({round(combined_solved/total_sorries*100, 2) if total_sorries > 0 else 0}%)")
    print("=" * 60)
    print()

    # Generate chart
    print("Generating chart...")
    generate_single_repo_chart(
        sorries_data,
        strategies_summary,
        args.repo,
        combined_solved,
        total_sorries,
        args.output_chart,
        show_percent=args.percent
    )

    # Build JSON output
    output_data = {
        "repo": args.repo,
        "total_sorries": total_sorries,
        "total_solved": combined_solved,
        "combined_rate": round(combined_solved / total_sorries * 100, 2) if total_sorries > 0 else 0,
        "strategies_summary": strategies_summary,
        "sorries": []
    }

    for sorry_id, data in sorries_data.items():
        sorry_entry = {
            "id": sorry_id,
            "location": data["sorry"].get("location", {}),
            "goal": data["sorry"].get("debug_info", {}).get("goal", ""),
            "url": data["sorry"].get("debug_info", {}).get("url", ""),
            "metadata": data["sorry"].get("metadata", {}),
            "solved_by": data["solved_by"],
            "proofs": data["proofs"]
        }
        output_data["sorries"].append(sorry_entry)

    # Sort sorries: solved ones first, then by path
    output_data["sorries"].sort(key=lambda x: (
        0 if x["solved_by"] else 1,
        x["location"].get("path", ""),
        x["location"].get("start_line", 0)
    ))

    # Write JSON output
    with open(args.output_json, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"JSON output written to {args.output_json}")
    print()
    print("Done!")


if __name__ == '__main__':
    main()
