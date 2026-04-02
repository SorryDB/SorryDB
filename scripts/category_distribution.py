#!/usr/bin/env python3
"""
Analyze the distribution of repository categories in the sorry dataset.
"""

import json
from collections import Counter
from pathlib import Path


def extract_repo_name(remote_url: str) -> str:
    """Extract 'owner/repo' from a GitHub URL."""
    # Handle URLs like https://github.com/AlexKontorovich/PrimeNumberTheoremAnd
    if remote_url.endswith(".git"):
        remote_url = remote_url[:-4]
    parts = remote_url.rstrip("/").split("/")
    return f"{parts[-2]}/{parts[-1]}"


def main():
    # Load the sorry dataset
    sorry_path = Path("deduplicated_all_reservoir_3_months.json")
    categories_path = Path("data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir_categories.json")

    with open(sorry_path) as f:
        sorry_data = json.load(f)

    with open(categories_path) as f:
        categories_data = json.load(f)

    # Build category lookup: repo_name -> category
    category_lookup = {
        cat["name"]: cat["category"]
        for cat in categories_data["categories"]
    }

    # Extract unique repos from sorry dataset
    sorries = sorry_data["sorries"]
    repo_names = set()
    for sorry in sorries:
        remote = sorry["repo"]["remote"]
        repo_name = extract_repo_name(remote)
        repo_names.add(repo_name)

    print(f"Total sorries: {len(sorries)}")
    print(f"Unique repos in sorry dataset: {len(repo_names)}")
    print(f"Repos with categories: {len(category_lookup)}")
    print()

    # Check for missing categories
    missing = repo_names - set(category_lookup.keys())
    if missing:
        print(f"WARNING: {len(missing)} repos missing categories:")
        for repo in sorted(missing):
            print(f"  - {repo}")
        print()
    else:
        print("All repos in sorry dataset have categories.")
        print()

    # Check for extra categories (repos in categories but not in sorry dataset)
    extra = set(category_lookup.keys()) - repo_names
    if extra:
        print(f"Note: {len(extra)} repos have categories but are not in sorry dataset:")
        for repo in sorted(extra):
            print(f"  - {repo}")
        print()

    # Calculate category distribution by sorry count
    sorry_category_counts = Counter()
    for sorry in sorries:
        remote = sorry["repo"]["remote"]
        repo_name = extract_repo_name(remote)
        category = category_lookup.get(repo_name, "unknown")
        sorry_category_counts[category] += 1

    # Calculate category distribution by repo count
    repo_category_counts = Counter()
    for repo_name in repo_names:
        category = category_lookup.get(repo_name, "unknown")
        repo_category_counts[category] += 1

    print("=" * 60)
    print("CATEGORY DISTRIBUTION BY SORRY COUNT")
    print("=" * 60)
    total_sorries = sum(sorry_category_counts.values())
    for category, count in sorry_category_counts.most_common():
        pct = 100 * count / total_sorries
        print(f"  {category:15} {count:5} ({pct:5.1f}%)")
    print()

    print("=" * 60)
    print("CATEGORY DISTRIBUTION BY REPO COUNT")
    print("=" * 60)
    total_repos = sum(repo_category_counts.values())
    for category, count in repo_category_counts.most_common():
        pct = 100 * count / total_repos
        print(f"  {category:15} {count:5} ({pct:5.1f}%)")
    print()

    # Detailed breakdown: repos per category with sorry counts
    print("=" * 60)
    print("DETAILED BREAKDOWN: REPOS BY CATEGORY")
    print("=" * 60)

    # Group repos by category
    repos_by_category = {}
    for repo_name in repo_names:
        category = category_lookup.get(repo_name, "unknown")
        if category not in repos_by_category:
            repos_by_category[category] = []
        repos_by_category[category].append(repo_name)

    # Count sorries per repo
    sorries_per_repo = Counter()
    for sorry in sorries:
        remote = sorry["repo"]["remote"]
        repo_name = extract_repo_name(remote)
        sorries_per_repo[repo_name] += 1

    for category in sorted(repos_by_category.keys()):
        repos = repos_by_category[category]
        print(f"\n{category.upper()} ({len(repos)} repos)")
        print("-" * 40)
        # Sort by sorry count descending
        for repo in sorted(repos, key=lambda r: -sorries_per_repo[r]):
            print(f"  {repo}: {sorries_per_repo[repo]} sorries")


if __name__ == "__main__":
    main()
