#!/usr/bin/env python3
"""
Analyze sorry lists and plot distributions.

Usage:
    python scripts/plot_blame_dates.py blame-dates <sorry_json_file> [--output <output_file>]
    python scripts/plot_blame_dates.py lean-versions <sorry_json_file> [--output <output_file>]
    python scripts/plot_blame_dates.py categories <sorry_json_file> <categories_json_file> [--output <output_file>]
    python scripts/plot_blame_dates.py compare-blame-dates <file1> <file2> [--output <output_file>] [--labels <label1> <label2>]

Example:
    python scripts/plot_blame_dates.py blame-dates data/2025_12_experiment_all_reservoir_3_months/10_3_months_reservoir.json
    python scripts/plot_blame_dates.py lean-versions data/2025_12_experiment_all_reservoir_3_months/10_3_months_reservoir.json -o lean_versions.pdf
    python scripts/plot_blame_dates.py categories data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir_categories.json -o categories.pdf
    python scripts/plot_blame_dates.py compare-blame-dates deduplicated_all_reservoir_3_months.json data/2025_12_experiment_all_reservoir/1000_all_reservoir.json -o compare.pdf --labels "3 Months" "Full"
"""

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

# Set font to match paper style
plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.serif'] = ['Times New Roman']


def load_sorries(json_path: str) -> list[dict]:
    """Load sorries from a JSON file."""
    with open(json_path, "r") as f:
        data = json.load(f)
    return data.get("sorries", [])


def extract_blame_dates(sorries: list[dict]) -> list[datetime]:
    """Extract and parse blame dates from sorries."""
    dates = []
    for sorry in sorries:
        blame_date_str = sorry.get("metadata", {}).get("blame_date")
        if blame_date_str:
            try:
                dt = datetime.fromisoformat(blame_date_str)
                dates.append(dt)
            except ValueError as e:
                print(f"Warning: Could not parse date '{blame_date_str}': {e}")
    return dates


def extract_lean_versions(sorries: list[dict]) -> list[str]:
    """Extract Lean versions from sorries."""
    versions = []
    for sorry in sorries:
        version = sorry.get("repo", {}).get("lean_version")
        if version:
            versions.append(version)
    return versions


def load_categories(json_path: str) -> list[dict]:
    """Load categories from a categories JSON file."""
    with open(json_path, "r") as f:
        data = json.load(f)
    return data.get("categories", [])


def build_repo_to_category_map(categories_data: list[dict]) -> dict[str, str]:
    """Build a mapping from repo name to category."""
    repo_to_category = {}
    for item in categories_data:
        name = item.get("name")
        category = item.get("category")
        if name and category:
            repo_to_category[name] = category
    return repo_to_category


def extract_sorry_categories(sorries: list[dict], repo_to_category: dict[str, str]) -> list[str]:
    """Extract categories for each sorry based on its repo."""
    categories = []
    for sorry in sorries:
        # Extract repo name from remote URL (e.g., "https://github.com/user/repo" -> "user/repo")
        remote = sorry.get("repo", {}).get("remote", "")
        if remote.startswith("https://github.com/"):
            repo_name = remote.replace("https://github.com/", "").rstrip("/")
        else:
            repo_name = remote

        category = repo_to_category.get(repo_name, "unknown")
        categories.append(category)
    return categories


def plot_blame_dates(
    dates: list[datetime],
    title: str = "Distribution of Sorry Blame Dates",
    output_path: str | None = None,
) -> None:
    """Create a histogram plot of blame dates with 2-month bins."""
    if not dates:
        print("No dates to plot.")
        return

    fig, ax = plt.subplots(figsize=(8, 4))

    # Create 2-month bin edges
    # Strip timezone info for comparison (convert to naive datetimes)
    dates_naive = [d.replace(tzinfo=None) if d.tzinfo else d for d in dates]
    min_date = min(dates_naive)
    max_date = max(dates_naive)

    # Round min_date down to start of its 2-month period (Dec, Feb, Apr, Jun, Aug, Oct)
    # This makes bins: Dec-Jan, Feb-Mar, Apr-May, Jun-Jul, Aug-Sep, Oct-Nov
    if min_date.month == 1:
        # January belongs to Dec-Jan bin, so start from previous December
        bin_start = datetime(min_date.year - 1, 12, 1)
    else:
        # Find the even month at or before min_date.month
        start_month = ((min_date.month) // 2) * 2
        if start_month == 0:
            start_month = 12
            bin_start = datetime(min_date.year - 1, start_month, 1)
        else:
            bin_start = datetime(min_date.year, start_month, 1)

    # Generate bin edges at 2-month intervals
    bin_edges = []
    current = bin_start
    while current <= max_date:
        bin_edges.append(current)
        # Move to next 2-month period
        new_month = current.month + 2
        new_year = current.year
        if new_month > 12:
            new_month -= 12
            new_year += 1
        current = datetime(new_year, new_month, 1)
    bin_edges.append(current)  # Add final edge

    # Convert to matplotlib date format
    bin_edges_num = mdates.date2num(bin_edges)
    dates_num = mdates.date2num(dates_naive)

    # Create histogram with 2-month bins
    counts, _, _ = ax.hist(dates_num, bins=bin_edges_num, edgecolor="black", alpha=0.7)

    # Find first and last non-empty bins to set x-axis limits
    first_nonempty = next(i for i, c in enumerate(counts) if c > 0)
    last_nonempty = len(counts) - 1 - next(i for i, c in enumerate(reversed(counts)) if c > 0)
    ax.set_xlim(bin_edges_num[first_nonempty], bin_edges_num[last_nonempty + 1])

    # Format x-axis as dates (show month and year, every 4 months)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))

    # Rotate labels for readability
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=14)

    ax.set_xlabel("Git Blame Date", fontsize=20)
    ax.set_ylabel("Number of Sorries", fontsize=20)
    ax.tick_params(axis='y', labelsize=16)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Plot saved to {output_path}")
    else:
        plt.show()


def plot_lean_versions(
    versions: list[str],
    title: str = "Distribution of Lean Versions",
    output_path: str | None = None,
) -> None:
    """Create a bar chart of Lean version distribution."""
    if not versions:
        print("No versions to plot.")
        return

    # Count versions and sort by version number
    version_counts = Counter(versions)

    # Sort versions naturally (v4.21.0 < v4.22.0 < v4.26.0-rc1)
    def version_sort_key(v: str) -> tuple:
        # Remove 'v' prefix and split by '.' and '-'
        v = v.lstrip("v")
        parts = v.replace("-", ".").split(".")
        result = []
        for part in parts:
            # Try to convert to int, otherwise keep as string
            try:
                result.append((0, int(part)))
            except ValueError:
                result.append((1, part))
        return tuple(result)

    sorted_versions = sorted(version_counts.keys(), key=version_sort_key)
    counts = [version_counts[v] for v in sorted_versions]

    fig, ax = plt.subplots(figsize=(8, 4))

    bars = ax.bar(range(len(sorted_versions)), counts, edgecolor="black", alpha=0.7)

    ax.set_xticks(range(len(sorted_versions)))
    ax.set_xticklabels(sorted_versions, rotation=45, ha="right", fontsize=14)

    ax.set_xlabel("Lean Version", fontsize=20)
    ax.set_ylabel("Number of Sorries", fontsize=20)
    ax.tick_params(axis='y', labelsize=16)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Add count labels on bars
    for bar, count in zip(bars, counts):
        height = bar.get_height()
        ax.annotate(
            f"{count}",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=14,
            fontweight="bold",
        )

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Plot saved to {output_path}")
    else:
        plt.show()


def plot_compare_blame_dates(
    dates_list: list[list[datetime]],
    labels: list[str],
    output_path: str | None = None,
) -> None:
    """Create stacked histogram plots of blame dates for multiple datasets."""
    if not dates_list or not any(dates_list):
        print("No dates to plot.")
        return

    n_datasets = len(dates_list)
    fig, axes = plt.subplots(n_datasets, 1, figsize=(8, 3 * n_datasets), sharex=True)

    if n_datasets == 1:
        axes = [axes]

    # Collect all dates to determine common bin edges
    all_dates_naive = []
    for dates in dates_list:
        dates_naive = [d.replace(tzinfo=None) if d.tzinfo else d for d in dates]
        all_dates_naive.extend(dates_naive)

    min_date = min(all_dates_naive)
    max_date = max(all_dates_naive)

    # Round min_date down to start of its 2-month period
    if min_date.month == 1:
        bin_start = datetime(min_date.year - 1, 12, 1)
    else:
        start_month = ((min_date.month) // 2) * 2
        if start_month == 0:
            start_month = 12
            bin_start = datetime(min_date.year - 1, start_month, 1)
        else:
            bin_start = datetime(min_date.year, start_month, 1)

    # Generate bin edges at 2-month intervals
    bin_edges = []
    current = bin_start
    while current <= max_date:
        bin_edges.append(current)
        new_month = current.month + 2
        new_year = current.year
        if new_month > 12:
            new_month -= 12
            new_year += 1
        current = datetime(new_year, new_month, 1)
    bin_edges.append(current)

    bin_edges_num = mdates.date2num(bin_edges)

    # Find global first/last non-empty bins across all datasets
    global_first = len(bin_edges_num)
    global_last = 0

    for dates in dates_list:
        dates_naive = [d.replace(tzinfo=None) if d.tzinfo else d for d in dates]
        dates_num = mdates.date2num(dates_naive)
        counts, _ = np.histogram(dates_num, bins=bin_edges_num)

        first_nonempty = next((i for i, c in enumerate(counts) if c > 0), len(counts))
        last_nonempty = len(counts) - 1 - next((i for i, c in enumerate(reversed(counts)) if c > 0), len(counts))

        global_first = min(global_first, first_nonempty)
        global_last = max(global_last, last_nonempty)

    # Plot each dataset
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']

    for i, (ax, dates, label) in enumerate(zip(axes, dates_list, labels)):
        dates_naive = [d.replace(tzinfo=None) if d.tzinfo else d for d in dates]
        dates_num = mdates.date2num(dates_naive)

        ax.hist(dates_num, bins=bin_edges_num, edgecolor="black", alpha=0.7, color=colors[i % len(colors)])
        ax.set_xlim(bin_edges_num[global_first], bin_edges_num[global_last + 1])

        ax.set_ylabel("# Sorries", fontsize=16)
        ax.tick_params(axis='y', labelsize=14)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        # Add label in top left
        ax.text(0.02, 0.95, f"{label} (n={len(dates)})", transform=ax.transAxes,
                fontsize=14, verticalalignment='top', horizontalalignment='left',
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    # Format x-axis on bottom plot only
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.setp(axes[-1].xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=14)
    axes[-1].set_xlabel("Git Blame Date", fontsize=18)

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Plot saved to {output_path}")
    else:
        plt.show()


def plot_categories(
    categories: list[str],
    title: str = "Distribution of Sorries by Category",
    output_path: str | None = None,
) -> None:
    """Create a bar chart of category distribution."""
    if not categories:
        print("No categories to plot.")
        return

    # Count categories and sort by count (descending)
    category_counts = Counter(categories)
    sorted_categories = sorted(category_counts.keys(), key=lambda x: category_counts[x], reverse=True)
    counts = [category_counts[c] for c in sorted_categories]

    # Color mapping for categories
    color_map = {
        "formalization": "#4CAF50",  # green
        "library": "#2196F3",        # blue
        "tooling": "#FF9800",        # orange
        "pedagogical": "#9C27B0",    # purple
        "benchmark": "#F44336",      # red
        "unknown": "#607D8B",        # gray
    }
    colors = [color_map.get(c, "#607D8B") for c in sorted_categories]

    fig, ax = plt.subplots(figsize=(8, 4))

    bars = ax.bar(range(len(sorted_categories)), counts, color=colors, edgecolor="black", alpha=0.8)

    ax.set_xticks(range(len(sorted_categories)))
    ax.set_xticklabels(sorted_categories, rotation=45, ha="right", fontsize=18)

    ax.set_xlabel("Category", fontsize=20)
    ax.set_ylabel("Number of Sorries", fontsize=20)
    ax.tick_params(axis='y', labelsize=16)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Add count labels on bars
    for bar, count in zip(bars, counts):
        height = bar.get_height()
        ax.annotate(
            f"{count}",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=14,
            fontweight="bold",
        )

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Plot saved to {output_path}")
    else:
        plt.show()


def main():
    parser = argparse.ArgumentParser(
        description="Analyze and plot distributions from sorry list JSON files."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Blame dates subcommand
    blame_parser = subparsers.add_parser(
        "blame-dates", help="Plot distribution of blame dates"
    )
    blame_parser.add_argument("json_file", help="Path to the sorry list JSON file")
    blame_parser.add_argument(
        "--output",
        "-o",
        help="Output file path for the plot. If not provided, displays interactively.",
    )
    blame_parser.add_argument("--title", "-t", help="Custom title for the plot")

    # Lean versions subcommand
    versions_parser = subparsers.add_parser(
        "lean-versions", help="Plot distribution of Lean versions"
    )
    versions_parser.add_argument("json_file", help="Path to the sorry list JSON file")
    versions_parser.add_argument(
        "--output",
        "-o",
        help="Output file path for the plot. If not provided, displays interactively.",
    )
    versions_parser.add_argument("--title", "-t", help="Custom title for the plot")

    # Categories subcommand
    categories_parser = subparsers.add_parser(
        "categories", help="Plot distribution of sorries by repository category"
    )
    categories_parser.add_argument("sorries_file", help="Path to the sorry list JSON file")
    categories_parser.add_argument("categories_file", help="Path to the categories JSON file")
    categories_parser.add_argument(
        "--output",
        "-o",
        help="Output file path for the plot. If not provided, displays interactively.",
    )
    categories_parser.add_argument("--title", "-t", help="Custom title for the plot")

    # Compare blame dates subcommand
    compare_parser = subparsers.add_parser(
        "compare-blame-dates", help="Plot stacked comparison of blame dates from two datasets"
    )
    compare_parser.add_argument("file1", help="Path to the first sorry list JSON file")
    compare_parser.add_argument("file2", help="Path to the second sorry list JSON file")
    compare_parser.add_argument(
        "--output",
        "-o",
        help="Output file path for the plot. If not provided, displays interactively.",
    )
    compare_parser.add_argument(
        "--labels",
        "-l",
        nargs=2,
        default=None,
        help="Labels for the two datasets (default: filenames)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "compare-blame-dates":
        file1_path = Path(args.file1)
        file2_path = Path(args.file2)

        if not file1_path.exists():
            print(f"Error: File not found: {file1_path}")
            return 1
        if not file2_path.exists():
            print(f"Error: File not found: {file2_path}")
            return 1

        print(f"Loading sorries from {file1_path}...")
        sorries1 = load_sorries(args.file1)
        print(f"Found {len(sorries1)} sorries")

        print(f"Loading sorries from {file2_path}...")
        sorries2 = load_sorries(args.file2)
        print(f"Found {len(sorries2)} sorries")

        dates1 = extract_blame_dates(sorries1)
        dates2 = extract_blame_dates(sorries2)
        print(f"Extracted {len(dates1)} and {len(dates2)} valid blame dates")

        labels = args.labels if args.labels else [file1_path.stem, file2_path.stem]
        plot_compare_blame_dates([dates1, dates2], labels, output_path=args.output)
        return 0

    if args.command == "categories":
        sorries_path = Path(args.sorries_file)
        categories_path = Path(args.categories_file)

        if not sorries_path.exists():
            print(f"Error: Sorries file not found: {sorries_path}")
            return 1
        if not categories_path.exists():
            print(f"Error: Categories file not found: {categories_path}")
            return 1

        print(f"Loading sorries from {sorries_path}...")
        sorries = load_sorries(args.sorries_file)
        print(f"Found {len(sorries)} sorries")

        print(f"Loading categories from {categories_path}...")
        categories_data = load_categories(args.categories_file)
        print(f"Found {len(categories_data)} repository categories")

        repo_to_category = build_repo_to_category_map(categories_data)
        categories = extract_sorry_categories(sorries, repo_to_category)

        # Check for unknown categories
        unknown_count = categories.count("unknown")
        if unknown_count > 0:
            print(f"Warning: {unknown_count} sorries have unknown categories")

        title = args.title or f"Distribution of Sorries by Category\n({sorries_path.name})"
        plot_categories(categories, title=title, output_path=args.output)
        return 0

    # For blame-dates and lean-versions commands
    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"Error: File not found: {json_path}")
        return 1

    print(f"Loading sorries from {json_path}...")
    sorries = load_sorries(args.json_file)
    print(f"Found {len(sorries)} sorries")

    if args.command == "blame-dates":
        dates = extract_blame_dates(sorries)
        print(f"Extracted {len(dates)} valid blame dates")
        title = args.title or f"Distribution of Sorry Blame Dates\n({json_path.name})"
        plot_blame_dates(dates, title=title, output_path=args.output)

    elif args.command == "lean-versions":
        versions = extract_lean_versions(sorries)
        print(f"Extracted {len(versions)} Lean versions")
        title = args.title or f"Distribution of Lean Versions\n({json_path.name})"
        plot_lean_versions(versions, title=title, output_path=args.output)

    return 0


if __name__ == "__main__":
    exit(main())
