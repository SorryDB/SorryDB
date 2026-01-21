#!/usr/bin/env python3
"""
Analyze sorry lists and plot distributions.

Usage:
    python scripts/plot_blame_dates.py blame-dates <sorry_json_file> [--output <output_file>]
    python scripts/plot_blame_dates.py lean-versions <sorry_json_file> [--output <output_file>]
    python scripts/plot_blame_dates.py categories <sorry_json_file> <categories_json_file> [--output <output_file>]

Example:
    python scripts/plot_blame_dates.py blame-dates data/2025_12_experiment_all_reservoir_3_months/10_3_months_reservoir.json
    python scripts/plot_blame_dates.py lean-versions data/2025_12_experiment_all_reservoir_3_months/10_3_months_reservoir.json -o lean_versions.png
    python scripts/plot_blame_dates.py categories data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir_categories.json -o categories.png
"""

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates


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
    """Create a histogram plot of blame dates."""
    if not dates:
        print("No dates to plot.")
        return

    fig, ax = plt.subplots(figsize=(12, 6))

    # Convert to matplotlib date format
    dates_num = mdates.date2num(dates)

    # Create histogram
    ax.hist(dates_num, bins=30, edgecolor="black", alpha=0.7)

    # Format x-axis as dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())

    # Rotate labels for readability
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    ax.set_xlabel("Blame Date")
    ax.set_ylabel("Number of Sorries")
    ax.set_title(title)

    # Add statistics
    min_date = min(dates)
    max_date = max(dates)
    stats_text = f"Total: {len(dates)} sorries\nRange: {min_date.date()} to {max_date.date()}"
    ax.text(
        0.02,
        0.98,
        stats_text,
        transform=ax.transAxes,
        verticalalignment="top",
        fontsize=10,
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
    )

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=150)
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

    fig, ax = plt.subplots(figsize=(12, 6))

    bars = ax.bar(range(len(sorted_versions)), counts, edgecolor="black", alpha=0.7)

    ax.set_xticks(range(len(sorted_versions)))
    ax.set_xticklabels(sorted_versions, rotation=45, ha="right")

    ax.set_xlabel("Lean Version")
    ax.set_ylabel("Number of Sorries")
    ax.set_title(title)

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
            fontsize=8,
        )

    # Add statistics
    stats_text = f"Total: {len(versions)} sorries\nUnique versions: {len(version_counts)}"
    ax.text(
        0.98,
        0.98,
        stats_text,
        transform=ax.transAxes,
        verticalalignment="top",
        horizontalalignment="right",
        fontsize=10,
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
    )

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=150)
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

    fig, ax = plt.subplots(figsize=(10, 6))

    bars = ax.bar(range(len(sorted_categories)), counts, color=colors, edgecolor="black", alpha=0.8)

    ax.set_xticks(range(len(sorted_categories)))
    ax.set_xticklabels(sorted_categories, rotation=45, ha="right")

    ax.set_xlabel("Category")
    ax.set_ylabel("Number of Sorries")
    ax.set_title(title)

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
            fontsize=10,
            fontweight="bold",
        )

    # Add statistics
    stats_text = f"Total: {len(categories)} sorries\nCategories: {len(category_counts)}"
    ax.text(
        0.98,
        0.98,
        stats_text,
        transform=ax.transAxes,
        verticalalignment="top",
        horizontalalignment="right",
        fontsize=10,
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
    )

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=150)
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

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

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
