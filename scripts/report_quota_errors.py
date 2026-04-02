#!/usr/bin/env python3
"""
Script to analyze experiment results and report sorries affected by quota exceeded errors.
"""

import argparse
import json
from pathlib import Path


QUOTA_ERROR_PATTERN = "You exceeded your current quota"


def analyze_quota_errors(experiment_dir: Path) -> dict:
    """
    Analyze an experiment directory and find sorries affected by quota errors.

    Returns a dict with analysis results.
    """
    result_file = experiment_dir / "result.json"

    if not result_file.exists():
        raise FileNotFoundError(f"result.json not found in {experiment_dir}")

    with open(result_file, "r") as f:
        results = json.load(f)

    total_sorries = len(results)
    affected_sorries = []

    for entry in results:
        sorry_id = entry.get("sorry", {}).get("id", "unknown")
        failed_attempts = entry.get("failed_attempts") or []

        # Count how many attempts had quota errors
        quota_error_count = sum(
            1 for attempt in failed_attempts
            if isinstance(attempt, str) and QUOTA_ERROR_PATTERN in attempt
        )

        if quota_error_count > 0:
            affected_sorries.append({
                "sorry_id": sorry_id,
                "repo": entry.get("sorry", {}).get("repo", {}).get("remote", "unknown"),
                "path": entry.get("sorry", {}).get("location", {}).get("path", "unknown"),
                "total_attempts": len(failed_attempts),
                "quota_errors": quota_error_count,
                "success": entry.get("success", False),
            })

    return {
        "total_sorries": total_sorries,
        "affected_sorries_count": len(affected_sorries),
        "affected_sorries": affected_sorries,
    }


def print_report(analysis: dict, verbose: bool = False):
    """Print a human-readable report of the analysis."""
    print("=" * 60)
    print("QUOTA ERROR ANALYSIS REPORT")
    print("=" * 60)
    print()
    print(f"Total sorries in experiment: {analysis['total_sorries']}")
    print(f"Sorries affected by quota errors: {analysis['affected_sorries_count']}")
    print(f"Percentage affected: {analysis['affected_sorries_count'] / analysis['total_sorries'] * 100:.1f}%")
    print()

    if analysis['affected_sorries']:
        # Summary statistics
        total_quota_errors = sum(s['quota_errors'] for s in analysis['affected_sorries'])
        total_attempts_affected = sum(s['total_attempts'] for s in analysis['affected_sorries'])
        successful_despite_errors = sum(1 for s in analysis['affected_sorries'] if s['success'])

        print(f"Total quota error occurrences: {total_quota_errors}")
        print(f"Sorries that succeeded despite quota errors: {successful_despite_errors}")
        print()

        if verbose:
            print("AFFECTED SORRIES:")
            print("-" * 60)
            for sorry in analysis['affected_sorries']:
                print(f"  ID: {sorry['sorry_id'][:16]}...")
                print(f"  Repo: {sorry['repo']}")
                print(f"  Path: {sorry['path']}")
                print(f"  Quota errors: {sorry['quota_errors']}/{sorry['total_attempts']} attempts")
                print(f"  Success: {sorry['success']}")
                print()


def main():
    parser = argparse.ArgumentParser(
        description="Analyze experiment results for quota exceeded errors"
    )
    parser.add_argument(
        "experiment_dir",
        type=Path,
        help="Path to the experiment directory (containing result.json)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show details for each affected sorry"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    analysis = analyze_quota_errors(args.experiment_dir)

    if args.json:
        print(json.dumps(analysis, indent=2))
    else:
        print_report(analysis, verbose=args.verbose)


if __name__ == "__main__":
    main()
