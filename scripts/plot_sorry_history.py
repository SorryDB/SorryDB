#!/usr/bin/env python3
"""
Plot stacked area chart of historical sorries from reservoir analysis.

Usage:
    python scripts/plot_sorry_history.py <sorries_json> [--output <output_file>] [--top-n 10] [--mode activity|count]

Example:
    python scripts/plot_sorry_history.py sorries.json -o sorry_history.png
    python scripts/plot_sorry_history.py sorries.json --top-n 5 --mode count
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

# Curated list of interesting formalization projects
CURATED_REPOS = [
    "fpvandoorn/carleson",
    "teorth/pfr",
    "kbuzzard/ClassFieldTheory",
    "leanprover-community/sphere-eversion",
    "thefundamentaltheor3m/Sphere-Packing-Lean",
]

# Set font to match paper style
plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.serif'] = ['Times New Roman']


def load_sorry_history(json_path: str) -> tuple[list[dict], str]:
    """
    Load sorry history from JSON file.

    Returns:
        - List of entries (commits or sorries)
        - Mode string: "accurate", "fast", or "legacy"
    """
    with open(json_path, "r") as f:
        data = json.load(f)

    # Check for explicit mode field
    mode = data.get("mode", None)
    if mode == "accurate":
        return data["commits"], "accurate"
    if mode == "fast":
        return data["commits"], "fast"

    # Legacy format detection (no mode field)
    if "commits" in data:
        # Old new format: has net changes
        return data["commits"], "fast"
    # Old format uses "sorries"
    return data.get("sorries", []), "legacy"


def get_repo_name(repo_url: str) -> str:
    """Extract short repo name from URL."""
    # https://github.com/owner/repo.git -> owner/repo
    name = repo_url.replace("https://github.com/", "").replace("git@github.com:", "")
    name = name.rstrip("/")
    if name.endswith(".git"):
        name = name[:-4]
    return name


def aggregate_by_month_and_repo(
    entries: list[dict],
    data_mode: str,
    plot_mode: str = "activity",
) -> tuple[list[datetime], dict[str, list[int]]]:
    """
    Aggregate sorry data by month and repository.

    Args:
        entries: List of commit or sorry entries
        data_mode: "accurate", "fast", or "legacy" - describes the input data format
        plot_mode: "activity" for cumulative additions, "count" for actual sorry count

    Returns:
        - List of month dates (sorted)
        - Dict mapping repo name to list of values per month
    """
    # For accurate mode with count plot, we track last known sorry_count per repo per month
    if data_mode == "accurate":
        # Group entries by repo and sort by date
        repo_entries = defaultdict(list)
        for entry in entries:
            date_str = entry.get("date")
            repo_url = entry.get("repo", "")
            if date_str:
                try:
                    dt = datetime.fromisoformat(date_str)
                    repo_entries[get_repo_name(repo_url)].append({
                        "date": dt,
                        "month_key": (dt.year, dt.month),
                        "sorry_count": entry.get("sorry_count", 0),
                    })
                except ValueError:
                    continue

        if not repo_entries:
            return [], {}

        # Get all months across all repos
        all_months = set()
        for entries_list in repo_entries.values():
            for e in entries_list:
                all_months.add(e["month_key"])

        sorted_months = sorted(all_months)
        month_dates = [datetime(year, month, 1) for year, month in sorted_months]

        # Build values per repo - use last known count for each month
        repo_values = {}
        for repo, entries_list in repo_entries.items():
            # Sort by date
            entries_list.sort(key=lambda e: e["date"])

            # For each month, find the last entry in or before that month
            values = []
            last_count = 0
            entry_idx = 0

            for month_key in sorted_months:
                # Advance to find latest entry <= this month
                while entry_idx < len(entries_list) and entries_list[entry_idx]["month_key"] <= month_key:
                    last_count = entries_list[entry_idx]["sorry_count"]
                    entry_idx += 1
                values.append(last_count)

            repo_values[repo] = values

        return month_dates, repo_values

    # Fast/legacy mode - use added/removed/net
    has_net = data_mode == "fast"

    # Group by (year, month) and repo
    monthly_data = defaultdict(lambda: defaultdict(lambda: {"added": 0, "net": 0}))

    for entry in entries:
        date_str = entry.get("date")
        repo_url = entry.get("repo", "")

        if not date_str:
            continue

        try:
            dt = datetime.fromisoformat(date_str)
            month_key = (dt.year, dt.month)
            repo_name = get_repo_name(repo_url)

            if has_net:
                # Fast format: use added and net
                monthly_data[month_key][repo_name]["added"] += entry.get("added", 0)
                monthly_data[month_key][repo_name]["net"] += entry.get("net", 0)
            else:
                # Legacy format: each entry counts as 1 activity
                monthly_data[month_key][repo_name]["added"] += 1
                monthly_data[month_key][repo_name]["net"] += 1
        except ValueError:
            continue

    if not monthly_data:
        return [], {}

    # Get sorted list of months
    sorted_months = sorted(monthly_data.keys())
    month_dates = [datetime(year, month, 1) for year, month in sorted_months]

    # Get all unique repos
    all_repos = set()
    for counts in monthly_data.values():
        all_repos.update(counts.keys())

    # Build cumulative values per repo
    repo_cumulative = {}
    for repo in all_repos:
        cumulative = []
        total = 0
        for month_key in sorted_months:
            if plot_mode == "count" and has_net:
                # Use net change for actual sorry count
                total += monthly_data[month_key][repo]["net"]
                # Don't allow negative counts
                total = max(0, total)
            else:
                # Use added for activity tracking
                total += monthly_data[month_key][repo]["added"]
            cumulative.append(total)
        repo_cumulative[repo] = cumulative

    return month_dates, repo_cumulative


def plot_repo_churn(
    json_path: str,
    repo: str,
    output_path: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    snapshot_path: str | None = None,
) -> None:
    """Plot weekly sorry additions and subtractions as a diverging bar chart."""
    print(f"Loading data from {json_path}...")
    entries, data_mode = load_sorry_history(json_path)

    if data_mode == "legacy":
        print("Error: This view requires 'accurate' or 'fast' format.")
        return

    # Filter to matching repo
    matching_entries = [e for e in entries if repo.lower() in e.get("repo", "").lower()]
    if not matching_entries:
        print(f"Error: No entries found for repo matching '{repo}'")
        return

    repo_name = get_repo_name(matching_entries[0]["repo"])
    print(f"Found {len(matching_entries)} commits for {repo_name}")

    # Group by week and separate additions/subtractions
    weekly_additions = {}
    weekly_subtractions = {}

    for entry in matching_entries:
        date_str = entry.get("date")
        if not date_str:
            continue
        try:
            dt = datetime.fromisoformat(date_str)
            # Get the Monday of that week
            week_start = dt - timedelta(days=dt.weekday())
            week_key = (week_start.year, week_start.month, week_start.day)

            net = entry.get("net", 0)
            if net > 0:
                weekly_additions[week_key] = weekly_additions.get(week_key, 0) + net
            elif net < 0:
                weekly_subtractions[week_key] = weekly_subtractions.get(week_key, 0) + net
        except ValueError:
            continue

    # Get all weeks
    all_weeks = sorted(set(weekly_additions.keys()) | set(weekly_subtractions.keys()))

    if not all_weeks:
        print("No valid data to plot.")
        return

    # Filter by start date if specified
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
            all_weeks = [w for w in all_weeks if datetime(w[0], w[1], w[2]) >= start_dt]
            print(f"Filtered to data from {start_date} onwards ({len(all_weeks)} weeks)")
        except ValueError:
            print(f"Invalid date format: {start_date}. Use YYYY-MM-DD.")
            return

    # Filter by end date if specified
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
            all_weeks = [w for w in all_weeks if datetime(w[0], w[1], w[2]) <= end_dt]
            print(f"Filtered to data until {end_date} ({len(all_weeks)} weeks)")
        except ValueError:
            print(f"Invalid date format: {end_date}. Use YYYY-MM-DD.")
            return

    if not all_weeks:
        print("No data in date range.")
        return

    week_dates = [datetime(w[0], w[1], w[2]) for w in all_weeks]
    additions = [weekly_additions.get(w, 0) for w in all_weeks]
    subtractions = [weekly_subtractions.get(w, 0) for w in all_weeks]

    # Load snapshot data if provided
    snapshot_dates = []
    if snapshot_path:
        try:
            with open(snapshot_path, "r") as f:
                snapshot_data = json.load(f)
            sorries = snapshot_data.get("sorries", [])
            for sorry in sorries:
                blame_date = sorry.get("metadata", {}).get("blame_date")
                if blame_date:
                    try:
                        dt = datetime.fromisoformat(blame_date)
                        snapshot_dates.append(dt)
                    except ValueError:
                        continue
            snapshot_dates.sort()
            print(f"Loaded {len(snapshot_dates)} sorries from snapshot")
            if snapshot_dates:
                print(f"  Date range: {snapshot_dates[0].strftime('%Y-%m-%d')} to {snapshot_dates[-1].strftime('%Y-%m-%d')}")
        except Exception as e:
            print(f"Warning: Could not load snapshot: {e}")

    # Create the plot
    fig, ax = plt.subplots(figsize=(12, 6))

    x = mdates.date2num(week_dates)
    bar_width = 5  # days

    # Plot additions (positive, green) and subtractions (negative, red)
    ax.bar(x, additions, width=bar_width, color='#E94F37', alpha=0.7, label='Sorries added')
    ax.bar(x, subtractions, width=bar_width, color='#4CAF50', alpha=0.7, label='Sorries resolved')

    # Add zero line
    ax.axhline(y=0, color='black', linewidth=0.5)

    # Add snapshot region if provided
    if snapshot_dates:
        x_snapshot = mdates.date2num(snapshot_dates)
        ax.axvspan(min(x_snapshot), max(x_snapshot), alpha=0.3, color='#CCCCCC')
        mid_x = (min(x_snapshot) + max(x_snapshot)) / 2
        ylim = ax.get_ylim()
        ax.annotate("Sorries sampled from\nthis region for evaluation",
                   xy=(mid_x, ylim[1] * 0.85),
                   ha='center', fontsize=10, color='#444444',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8, edgecolor='#888888'))

    # Format axes
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=11)

    ax.set_xlabel("Date", fontsize=14)
    ax.set_ylabel("Sorries added / resolved per week", fontsize=14)
    ax.legend(loc='upper left', fontsize=10)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"\nPlot saved to {output_path}")
    else:
        plt.show()


def plot_repo_with_commits(
    json_path: str,
    repo: str,
    output_path: str | None = None,
    start_date: str | None = None,
    daily: bool = False,
    stacked: bool = False,
    snapshot_path: str | None = None,
) -> None:
    """Plot sorry count for a single repo with commit histogram overlay."""
    print(f"Loading data from {json_path}...")
    entries, data_mode = load_sorry_history(json_path)

    if data_mode == "legacy":
        print("Error: This view requires 'accurate' or 'fast' format.")
        return

    # Filter to matching repo
    matching_entries = [e for e in entries if repo.lower() in e.get("repo", "").lower()]
    if not matching_entries:
        print(f"Error: No entries found for repo matching '{repo}'")
        return

    repo_name = get_repo_name(matching_entries[0]["repo"])
    print(f"Found {len(matching_entries)} commits for {repo_name}")

    # Group commits by day or week
    commit_count = {}
    sorry_data = {}

    for entry in matching_entries:
        date_str = entry.get("date")
        if not date_str:
            continue
        try:
            dt = datetime.fromisoformat(date_str)
            if daily:
                time_key = (dt.year, dt.month, dt.day)
            else:
                # Get the Monday of that week
                week_start = dt - timedelta(days=dt.weekday())
                time_key = (week_start.year, week_start.month, week_start.day)

            # Count commits
            commit_count[time_key] = commit_count.get(time_key, 0) + 1
            # Sum net sorry changes
            sorry_data[time_key] = sorry_data.get(time_key, 0) + entry.get("net", 0)
        except ValueError:
            continue

    if not sorry_data:
        print("No valid data to plot.")
        return

    # Sort time periods and compute cumulative sorry count
    sorted_times = sorted(sorry_data.keys())
    time_dates = [datetime(k[0], k[1], k[2]) for k in sorted_times]
    sorry_counts = []
    cumulative = 0
    for k in sorted_times:
        cumulative += sorry_data[k]
        cumulative = max(0, cumulative)  # Don't go negative
        sorry_counts.append(cumulative)

    time_label = "days" if daily else "weeks"

    # Filter by start date if specified
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
            # Filter sorry data
            start_idx = next((i for i, d in enumerate(time_dates) if d >= start_dt), len(time_dates))
            if start_idx >= len(time_dates):
                print(f"No data after {start_date}")
                return
            time_dates = time_dates[start_idx:]
            sorry_counts = sorry_counts[start_idx:]
            # Filter commit counts too
            commit_count = {k: v for k, v in commit_count.items()
                           if datetime(k[0], k[1], k[2]) >= start_dt}
            print(f"Filtered to data from {start_date} onwards ({len(time_dates)} {time_label})")
        except ValueError:
            print(f"Invalid date format: {start_date}. Use YYYY-MM-DD.")
            return

    # Build commit data for bar chart
    bar_dates = sorted([datetime(k[0], k[1], k[2]) for k in commit_count.keys()])
    commit_counts = [commit_count[(d.year, d.month, d.day)] for d in bar_dates]

    x_commits = mdates.date2num(bar_dates)
    x_sorry = mdates.date2num(time_dates)
    bar_width = 1 if daily else 5  # days
    ylabel = "Commits per Day" if daily else "Commits per Week"

    # Load snapshot data if provided
    snapshot_dates = []
    if snapshot_path:
        try:
            with open(snapshot_path, "r") as f:
                snapshot_data = json.load(f)
            sorries = snapshot_data.get("sorries", [])
            for sorry in sorries:
                blame_date = sorry.get("metadata", {}).get("blame_date")
                if blame_date:
                    try:
                        dt = datetime.fromisoformat(blame_date)
                        snapshot_dates.append(dt)
                    except ValueError:
                        continue
            snapshot_dates.sort()
            print(f"Loaded {len(snapshot_dates)} sorries from snapshot")
            if snapshot_dates:
                print(f"  Date range: {snapshot_dates[0].strftime('%Y-%m-%d')} to {snapshot_dates[-1].strftime('%Y-%m-%d')}")
        except Exception as e:
            print(f"Warning: Could not load snapshot: {e}")

    if stacked:
        # Create two subplots with shared x-axis
        fig, (ax_sorry, ax_commits) = plt.subplots(2, 1, figsize=(12, 8), sharex=True,
                                                    gridspec_kw={'height_ratios': [1, 1]})

        # Top plot: Sorry count
        ax_sorry.plot(x_sorry, sorry_counts, color='#E94F37', linewidth=2.5)
        ax_sorry.set_ylabel("Number of remaining sorries in repository", fontsize=14)
        ax_sorry.set_ylim(bottom=0)
        ax_sorry.spines['top'].set_visible(False)
        ax_sorry.spines['right'].set_visible(False)
        ax_sorry.fill_between(x_sorry, sorry_counts, alpha=0.3, color='#E94F37')

        # Add snapshot markers if provided
        if snapshot_dates:
            x_snapshot = mdates.date2num(snapshot_dates)
            # Shade the date range
            ax_sorry.axvspan(min(x_snapshot), max(x_snapshot), alpha=0.3, color='#CCCCCC')
            # Add annotation for the region
            mid_x = (min(x_snapshot) + max(x_snapshot)) / 2
            ax_sorry.annotate("Sorries sampled from\nthis region for evaluation",
                             xy=(mid_x, ax_sorry.get_ylim()[1] * 0.85),
                             ha='center', fontsize=10, color='#444444',
                             bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8, edgecolor='#888888'))

        # Bottom plot: Commits histogram
        ax_commits.bar(x_commits, commit_counts, width=bar_width, alpha=0.7, color='#2E86AB')
        ax_commits.set_ylabel(ylabel, fontsize=14)
        ax_commits.set_ylim(bottom=0)
        ax_commits.spines['top'].set_visible(False)
        ax_commits.spines['right'].set_visible(False)

        # Format x-axis on bottom plot
        ax_commits.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        ax_commits.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.setp(ax_commits.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=11)
        ax_commits.set_xlabel("Date", fontsize=14)
    else:
        # Create the plot with dual y-axis (original behavior)
        fig, ax1 = plt.subplots(figsize=(12, 6))

        # Plot commit histogram on primary axis (bars)
        ax1.bar(x_commits, commit_counts, width=bar_width, alpha=0.4, color='#2E86AB', label='Commits')
        ax1.set_ylabel(ylabel, fontsize=14, color='#2E86AB')
        ax1.tick_params(axis='y', labelcolor='#2E86AB')
        ax1.set_ylim(bottom=0)

        # Create secondary y-axis for sorry count
        ax2 = ax1.twinx()
        ax2.plot(x_sorry, sorry_counts, color='#E94F37', linewidth=2.5, label='Sorry Count')
        ax2.set_ylabel("Sorry Count", fontsize=14, color='#E94F37')
        ax2.tick_params(axis='y', labelcolor='#E94F37')
        ax2.set_ylim(bottom=0)

        # Format x-axis
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=11)

        ax1.set_xlabel("Date", fontsize=14)
        ax1.set_title(f"Sorry Count and Commit Activity: {repo_name}", fontsize=16)

        # Add snapshot markers if provided
        if snapshot_dates:
            x_snapshot = mdates.date2num(snapshot_dates)
            # Shade the date range
            ax1.axvspan(min(x_snapshot), max(x_snapshot), alpha=0.15, color='#4CAF50',
                       label='Snapshot date range')
            # Draw vertical lines for each sorry
            for x in x_snapshot:
                ax1.axvline(x, color='#4CAF50', alpha=0.5, linewidth=0.8)

        # Combined legend
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=10)

        ax1.spines['top'].set_visible(False)
        ax2.spines['top'].set_visible(False)

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"\nPlot saved to {output_path}")
    else:
        plt.show()


def plot_total_sorries(
    json_path: str,
    output_path: str | None = None,
    start_date: str | None = None,
) -> None:
    """Plot total sorries across all repos as a single line."""
    print(f"Loading data from {json_path}...")
    entries, data_mode = load_sorry_history(json_path)

    format_desc = {
        "accurate": "accurate mode (absolute counts)",
        "fast": "fast mode (diff parsing)",
        "legacy": "legacy format",
    }
    print(f"Found {len(entries)} entries (format: {format_desc.get(data_mode, data_mode)})")

    if data_mode == "legacy":
        print("Error: Total view requires 'accurate' or 'fast' format.")
        return

    month_dates, repo_cumulative = aggregate_by_month_and_repo(entries, data_mode, "count")

    if not month_dates:
        print("No valid data to plot.")
        return

    # Filter by start date if specified
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
            start_idx = next((i for i, d in enumerate(month_dates) if d >= start_dt), len(month_dates))
            if start_idx >= len(month_dates):
                print(f"No data after {start_date}")
                return
            month_dates = month_dates[start_idx:]
            repo_cumulative = {repo: counts[start_idx:] for repo, counts in repo_cumulative.items()}
            print(f"Filtered to data from {start_date} onwards ({len(month_dates)} months)")
        except ValueError:
            print(f"Invalid date format: {start_date}. Use YYYY-MM-DD.")
            return

    # Sum across all repos for each month
    total_per_month = [0] * len(month_dates)
    for repo, counts in repo_cumulative.items():
        for i, count in enumerate(counts):
            total_per_month[i] += count

    print(f"\nTotal sorries across {len(repo_cumulative)} repos:")
    print(f"  Start: {total_per_month[0]:,}")
    print(f"  Peak: {max(total_per_month):,}")
    print(f"  Current: {total_per_month[-1]:,}")

    # Create the plot
    fig, ax = plt.subplots(figsize=(12, 6))

    x_data = mdates.date2num(month_dates)
    ax.plot(x_data, total_per_month, color='#2E86AB', linewidth=2.5)
    ax.fill_between(x_data, total_per_month, alpha=0.3, color='#2E86AB')

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=12)

    ax.set_xlabel("Date", fontsize=16)
    ax.set_ylabel("Total Sorry Count", fontsize=16)
    ax.tick_params(axis='both', labelsize=12)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.set_ylim(bottom=0)

    # Add comma formatting to y-axis
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"\nPlot saved to {output_path}")
    else:
        plt.show()


def aggregate_by_week_and_repo(
    entries: list[dict],
    data_mode: str,
) -> tuple[list[datetime], dict[str, list[int]]]:
    """Aggregate sorry data by week and repository for smoother lines."""
    if data_mode == "legacy":
        return [], {}

    # Group by week and repo
    weekly_data = defaultdict(lambda: defaultdict(int))

    for entry in entries:
        date_str = entry.get("date")
        repo_url = entry.get("repo", "")
        if not date_str:
            continue
        try:
            dt = datetime.fromisoformat(date_str)
            week_start = dt - timedelta(days=dt.weekday())
            week_key = (week_start.year, week_start.month, week_start.day)
            repo_name = get_repo_name(repo_url)
            weekly_data[week_key][repo_name] += entry.get("net", 0)
        except ValueError:
            continue

    if not weekly_data:
        return [], {}

    sorted_weeks = sorted(weekly_data.keys())
    week_dates = [datetime(k[0], k[1], k[2]) for k in sorted_weeks]

    # Get all repos
    all_repos = set()
    for counts in weekly_data.values():
        all_repos.update(counts.keys())

    # Build cumulative counts per repo
    repo_cumulative = {}
    for repo in all_repos:
        cumulative = []
        total = 0
        for week_key in sorted_weeks:
            total += weekly_data[week_key][repo]
            total = max(0, total)
            cumulative.append(total)
        repo_cumulative[repo] = cumulative

    return week_dates, repo_cumulative


def aggregate_by_day_and_repo(
    entries: list[dict],
    data_mode: str,
) -> tuple[list[datetime], dict[str, list[int]]]:
    """Aggregate sorry data by day and repository for smoothest lines."""
    if data_mode == "legacy":
        return [], {}

    # Group by day and repo
    daily_data = defaultdict(lambda: defaultdict(int))

    for entry in entries:
        date_str = entry.get("date")
        repo_url = entry.get("repo", "")
        if not date_str:
            continue
        try:
            dt = datetime.fromisoformat(date_str)
            day_key = (dt.year, dt.month, dt.day)
            repo_name = get_repo_name(repo_url)
            daily_data[day_key][repo_name] += entry.get("net", 0)
        except ValueError:
            continue

    if not daily_data:
        return [], {}

    sorted_days = sorted(daily_data.keys())
    day_dates = [datetime(k[0], k[1], k[2]) for k in sorted_days]

    # Get all repos
    all_repos = set()
    for counts in daily_data.values():
        all_repos.update(counts.keys())

    # Build cumulative counts per repo
    repo_cumulative = {}
    for repo in all_repos:
        cumulative = []
        total = 0
        for day_key in sorted_days:
            total += daily_data[day_key][repo]
            total = max(0, total)
            cumulative.append(total)
        repo_cumulative[repo] = cumulative

    return day_dates, repo_cumulative


def plot_aligned_lines(
    json_path: str,
    output_path: str | None = None,
    top_n: int = 10,
    rank_by: str = "final",
    use_raw_dates: bool = False,
    skip: int = 0,
    start_date: str | None = None,
    split_by_size: bool = False,
    curated: bool = False,
    repo: str | None = None,
    weekly: bool = False,
    daily: bool = False,
) -> None:
    """Create a line chart showing repo trajectories."""
    print(f"Loading data from {json_path}...")
    entries, data_mode = load_sorry_history(json_path)

    format_desc = {
        "accurate": "accurate mode (absolute counts)",
        "fast": "fast mode (diff parsing)",
        "legacy": "legacy format",
    }
    print(f"Found {len(entries)} entries (format: {format_desc.get(data_mode, data_mode)})")

    if data_mode == "legacy":
        print("Error: Line chart view requires 'accurate' or 'fast' format.")
        return

    if daily:
        time_dates, repo_cumulative = aggregate_by_day_and_repo(entries, data_mode)
        time_label = "days"
    elif weekly:
        time_dates, repo_cumulative = aggregate_by_week_and_repo(entries, data_mode)
        time_label = "weeks"
    else:
        time_dates, repo_cumulative = aggregate_by_month_and_repo(entries, data_mode, "count")
        time_label = "months"

    if not time_dates:
        print("No valid data to plot.")
        return

    # Filter by start date if specified
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
            # Find the index of the first date >= start_date
            start_idx = next((i for i, d in enumerate(time_dates) if d >= start_dt), len(time_dates))
            if start_idx >= len(time_dates):
                print(f"No data after {start_date}")
                return
            time_dates = time_dates[start_idx:]
            repo_cumulative = {repo: counts[start_idx:] for repo, counts in repo_cumulative.items()}
            print(f"Filtered to data from {start_date} onwards ({len(time_dates)} {time_label})")
        except ValueError:
            print(f"Invalid date format: {start_date}. Use YYYY-MM-DD.")
            return

    # Compute stats for each repo
    repo_stats = {}
    for repo_name, counts in repo_cumulative.items():
        final = counts[-1]
        peak = max(counts)
        resolved = peak - final
        # Find first month with non-zero count
        first_nonzero = next((i for i, c in enumerate(counts) if c > 0), len(counts))
        repo_stats[repo_name] = {
            "final": final,
            "peak": peak,
            "resolved": resolved,
            "first_nonzero": first_nonzero,
        }

    # Use specific repo, curated list, or sort by rank_by parameter
    if repo:
        # Filter to specific repo (match by full name or partial)
        matching = [r for r in repo_stats.keys() if repo.lower() in r.lower()]
        if not matching:
            print(f"Error: No repo matching '{repo}' found in data.")
            return
        top_repos = matching
        rank_label = f"repo: {repo}"
        print(f"Found {len(matching)} matching repo(s): {matching}")
    elif curated:
        # Filter to curated repos that exist in the data
        top_repos = [r for r in CURATED_REPOS if r in repo_stats]
        missing = [r for r in CURATED_REPOS if r not in repo_stats]
        if missing:
            print(f"Warning: Curated repos not found in data: {missing}")
        rank_label = "curated list"
    else:
        if rank_by == "resolved":
            sorted_repos = sorted(repo_stats.keys(), key=lambda r: repo_stats[r]["resolved"], reverse=True)
            rank_label = "resolved sorries (peak - current)"
        else:
            sorted_repos = sorted(repo_stats.keys(), key=lambda r: repo_stats[r]["final"], reverse=True)
            rank_label = "sorry count"

        top_repos = sorted_repos[skip:skip + top_n]

    if skip > 0:
        print(f"\nRepositories ranked {skip + 1}-{skip + len(top_repos)} by {rank_label}:")
    else:
        print(f"\nTop {len(top_repos)} repositories by {rank_label}:")
    for repo in top_repos:
        stats = repo_stats[repo]
        if rank_by == "resolved":
            print(f"  {repo}: peak={stats['peak']}, current={stats['final']}, resolved={stats['resolved']}")
        else:
            print(f"  {repo}: {stats['final']}")

    # Split by size into 4 subplots
    if split_by_size:
        # Sort repos by peak and split into 4 roughly equal groups
        repos_by_peak = sorted(top_repos, key=lambda r: repo_stats[r]["peak"], reverse=True)
        n = len(repos_by_peak)
        quarter = max(1, n // 4)

        tiers = [
            ("Large", repos_by_peak[:quarter]),
            ("Medium", repos_by_peak[quarter:2*quarter]),
            ("Small", repos_by_peak[2*quarter:3*quarter]),
            ("Tiny", repos_by_peak[3*quarter:]),
        ]

        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        axes = axes.flatten()

        for ax, (tier_name, tier_repos) in zip(axes, tiers):
            if not tier_repos:
                ax.set_visible(False)
                continue

            # Get color for each repo in this tier
            tier_colors = plt.cm.hsv(np.linspace(0, 0.9, len(tier_repos)))

            for repo, color in zip(tier_repos, tier_colors):
                counts = repo_cumulative[repo]
                if use_raw_dates:
                    x_data = mdates.date2num(time_dates)
                    y_data = counts
                else:
                    first_idx = repo_stats[repo]["first_nonzero"]
                    y_data = counts[first_idx:]
                    x_data = list(range(len(y_data)))

                ax.plot(x_data, y_data, label=repo.split('/')[-1], color=color, linewidth=2)

            if use_raw_dates:
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
                ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
                plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=9)

            peak_range = f"{min(repo_stats[r]['peak'] for r in tier_repos)}-{max(repo_stats[r]['peak'] for r in tier_repos)}"
            ax.set_title(f"{tier_name} (peak: {peak_range})", fontsize=12)
            ax.set_ylabel("Sorry Count", fontsize=10)
            ax.set_ylim(bottom=0)
            ax.legend(loc='upper right', fontsize=7, framealpha=0.9)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)

        fig.suptitle("Sorry Count Over Time by Project Size", fontsize=16)
        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            print(f"\nPlot saved to {output_path}")
        else:
            plt.show()
        return

    # Create the plot (single chart)
    fig, ax = plt.subplots(figsize=(12, 6))

    # Use tab20 for up to 20, or hsv for more distinct colors
    if len(top_repos) <= 10:
        colors = plt.cm.tab10(np.linspace(0, 1, len(top_repos)))
    elif len(top_repos) <= 20:
        colors = plt.cm.tab20(np.linspace(0, 1, len(top_repos)))
    else:
        # For 20+ repos, use hsv colormap for maximum distinction
        colors = plt.cm.hsv(np.linspace(0, 0.9, len(top_repos)))

    for repo, color in zip(top_repos, colors):
        counts = repo_cumulative[repo]

        if use_raw_dates:
            # Use actual dates
            x_data = mdates.date2num(time_dates)
            y_data = counts
        else:
            # Align: start from first non-zero
            first_idx = repo_stats[repo]["first_nonzero"]
            y_data = counts[first_idx:]
            x_data = list(range(len(y_data)))

        ax.plot(x_data, y_data, label=repo, color=color, linewidth=2)

    if use_raw_dates:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        if daily:
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        elif weekly:
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        else:
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=12)
        ax.set_xlabel("Date", fontsize=16)
        ax.set_title("Sorry Count Over Time in Lean Repositories", fontsize=18)
    else:
        time_unit = "Days" if daily else ("Weeks" if weekly else "Months")
        ax.set_xlabel(f"{time_unit} Since First Sorry", fontsize=16)
        ax.set_title("Sorry Count Over Time (Aligned to Project Start)", fontsize=18)
        ax.set_xlim(left=0)

    ax.set_ylabel("Sorry Count", fontsize=16)
    ax.tick_params(axis='both', labelsize=12)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Adjust legend based on number of repos
    if len(top_repos) > 15:
        # Many repos: put legend below chart in multiple columns
        ax.legend(
            loc='upper center',
            bbox_to_anchor=(0.5, -0.15),
            ncol=3,
            fontsize=8,
            framealpha=0.9,
        )
        plt.subplots_adjust(bottom=0.3)
    else:
        ax.legend(loc='upper right', fontsize=9, framealpha=0.9)

    ax.set_ylim(bottom=0)

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"\nPlot saved to {output_path}")
    else:
        plt.show()


def plot_stacked_area(
    json_path: str,
    output_path: str | None = None,
    top_n: int = 10,
    mode: str = "activity",
    rank_by: str = "final",
    no_other: bool = False,
) -> None:
    """Create a stacked area chart of sorry history."""
    print(f"Loading data from {json_path}...")
    entries, data_mode = load_sorry_history(json_path)

    format_desc = {
        "accurate": "accurate mode (absolute counts)",
        "fast": "fast mode (diff parsing)",
        "legacy": "legacy format",
    }
    print(f"Found {len(entries)} entries (format: {format_desc.get(data_mode, data_mode)})")

    if mode == "count" and data_mode == "legacy":
        print("Warning: 'count' mode requires 'accurate' or 'fast' format. Falling back to 'activity' mode.")
        mode = "activity"

    month_dates, repo_cumulative = aggregate_by_month_and_repo(entries, data_mode, mode)

    if not month_dates:
        print("No valid data to plot.")
        return

    print(f"Data spans {len(month_dates)} months")
    print(f"Found {len(repo_cumulative)} unique repositories")

    # Compute stats for each repo
    repo_stats = {}
    for repo, counts in repo_cumulative.items():
        final = counts[-1]
        peak = max(counts)
        resolved = peak - final
        repo_stats[repo] = {"final": final, "peak": peak, "resolved": resolved}

    # Sort repos based on rank_by parameter
    if rank_by == "resolved":
        sorted_repos = sorted(repo_stats.keys(), key=lambda r: repo_stats[r]["resolved"], reverse=True)
        rank_label = "resolved sorries (peak - current)"
    else:
        sorted_repos = sorted(repo_stats.keys(), key=lambda r: repo_stats[r]["final"], reverse=True)
        rank_label = "sorry count"

    # Take top N repos, aggregate rest as "Other"
    top_repos = sorted_repos[:top_n]
    other_repos = sorted_repos[top_n:]

    print(f"\nTop {len(top_repos)} repositories by {rank_label}:")
    for repo in top_repos:
        stats = repo_stats[repo]
        if rank_by == "resolved":
            print(f"  {repo}: peak={stats['peak']}, current={stats['final']}, resolved={stats['resolved']}")
        else:
            print(f"  {repo}: {stats['final']}")

    if other_repos and not no_other:
        if rank_by == "resolved":
            other_total = sum(repo_stats[r]["resolved"] for r in other_repos)
        else:
            other_total = sum(repo_stats[r]["final"] for r in other_repos)
        print(f"  Other ({len(other_repos)} repos): {other_total}")

    # Prepare data for stacking
    # Reverse order so largest is at bottom
    plot_repos = list(reversed(top_repos))

    # Add "Other" category if there are more repos (and not excluded)
    if other_repos and not no_other:
        other_cumulative = [0] * len(month_dates)
        for repo in other_repos:
            for i, count in enumerate(repo_cumulative[repo]):
                other_cumulative[i] += count
        plot_repos = ["Other"] + plot_repos
        repo_cumulative["Other"] = other_cumulative

    # Convert to numpy arrays for stackplot
    y_data = np.array([repo_cumulative[repo] for repo in plot_repos])
    x_data = mdates.date2num(month_dates)

    # Create the plot
    fig, ax = plt.subplots(figsize=(12, 6))

    # Use a colormap
    colors = plt.cm.tab20(np.linspace(0, 1, len(plot_repos)))

    # Create stacked area chart
    ax.stackplot(x_data, y_data, labels=plot_repos, colors=colors, alpha=0.8)

    # Format x-axis as dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=12)

    ax.set_xlabel("Date", fontsize=16)
    if mode == "count":
        ax.set_ylabel("Sorry Count", fontsize=16)
        title = "Sorry Count Over Time in Lean Reservoir Repositories"
    else:
        ax.set_ylabel("Cumulative Sorry Additions", fontsize=16)
        title = "Cumulative Sorry Additions in Lean Reservoir Repositories"
    ax.tick_params(axis='y', labelsize=12)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Add legend (reversed to match stacking order visually)
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(
        reversed(handles),
        reversed(labels),
        loc='upper left',
        fontsize=10,
        framealpha=0.9,
    )

    ax.set_title(title, fontsize=18)

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"\nPlot saved to {output_path}")
    else:
        plt.show()


def main():
    parser = argparse.ArgumentParser(
        description="Plot stacked area chart of historical sorries from reservoir analysis."
    )
    parser.add_argument(
        "json_file",
        help="Path to the sorry history JSON file (from analyze-reservoir-history)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path for the plot. If not provided, displays interactively.",
    )
    parser.add_argument(
        "--top-n", "-n",
        type=int,
        default=10,
        help="Number of top repositories to show individually (default: 10). Rest are grouped as 'Other'.",
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["activity", "count"],
        default="activity",
        help="'activity': cumulative sorry additions (default). 'count': actual sorry count over time (requires new format with net changes).",
    )
    parser.add_argument(
        "--rank-by", "-r",
        choices=["final", "resolved"],
        default="final",
        help="'final': rank by current sorry count (default). 'resolved': rank by (peak - current), showing repos that resolved the most sorries.",
    )
    parser.add_argument(
        "--no-other",
        action="store_true",
        help="Exclude 'Other' category from the chart (show only top N repos).",
    )
    parser.add_argument(
        "--skip",
        type=int,
        default=0,
        help="Skip the top N repositories (e.g., --skip 3 to exclude top 3 and show ranks 4-N).",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Only show data from this date onwards (format: YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Only show data until this date (format: YYYY-MM-DD).",
    )
    parser.add_argument(
        "--lines",
        action="store_true",
        help="Use line chart instead of stacked area (better for comparing individual repos).",
    )
    parser.add_argument(
        "--align-start",
        action="store_true",
        help="With --lines, align all repos to start at month 0. Without this, uses raw dates.",
    )
    parser.add_argument(
        "--split-by-size",
        action="store_true",
        help="Split into 4 subplots by peak sorry count (large/medium/small/tiny).",
    )
    parser.add_argument(
        "--curated",
        action="store_true",
        help="Use curated list of interesting formalization projects instead of top N.",
    )
    parser.add_argument(
        "--total",
        action="store_true",
        help="Plot total sorries across all repos (single line showing ecosystem-wide sorry count).",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Plot a specific repo by name (e.g., 'RemyDegenne/brownian-motion' or just 'brownian-motion').",
    )
    parser.add_argument(
        "--with-commits",
        action="store_true",
        help="Overlay a histogram of commit activity on the sorry count chart.",
    )
    parser.add_argument(
        "--weekly",
        action="store_true",
        help="Use weekly data instead of monthly for smoother lines.",
    )
    parser.add_argument(
        "--daily",
        action="store_true",
        help="Use daily data for smoothest lines.",
    )
    parser.add_argument(
        "--stacked",
        action="store_true",
        help="Show commits and sorry count in separate stacked subplots instead of overlaid.",
    )
    parser.add_argument(
        "--snapshot",
        type=str,
        default=None,
        help="Path to a SorryDB snapshot JSON file. Overlays markers showing when each sorry was introduced.",
    )
    parser.add_argument(
        "--churn",
        action="store_true",
        help="Show weekly sorry additions and subtractions as a diverging bar chart.",
    )

    args = parser.parse_args()

    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"Error: File not found: {json_path}")
        return 1

    if args.churn and args.repo:
        plot_repo_churn(
            json_path=str(json_path),
            repo=args.repo,
            output_path=args.output,
            start_date=args.start_date,
            end_date=args.end_date,
            snapshot_path=args.snapshot,
        )
    elif args.with_commits and args.repo:
        plot_repo_with_commits(
            json_path=str(json_path),
            repo=args.repo,
            output_path=args.output,
            start_date=args.start_date,
            daily=args.daily,
            stacked=args.stacked,
            snapshot_path=args.snapshot,
        )
    elif args.total:
        plot_total_sorries(
            json_path=str(json_path),
            output_path=args.output,
            start_date=args.start_date,
        )
    elif args.lines or args.repo:
        plot_aligned_lines(
            json_path=str(json_path),
            output_path=args.output,
            top_n=args.top_n,
            rank_by=args.rank_by,
            use_raw_dates=not args.align_start,
            skip=args.skip,
            start_date=args.start_date,
            split_by_size=args.split_by_size,
            curated=args.curated,
            repo=args.repo,
            weekly=args.weekly,
            daily=args.daily,
        )
    else:
        plot_stacked_area(
            json_path=str(json_path),
            output_path=args.output,
            top_n=args.top_n,
            mode=args.mode,
            rank_by=args.rank_by,
            no_other=args.no_other,
        )

    return 0


if __name__ == "__main__":
    exit(main())
