#!/usr/bin/env python3
"""
Script to extract sorries that failed (quota errors or success=false) for rerunning.
"""

import argparse
import json
from pathlib import Path


QUOTA_ERROR_PATTERN = "You exceeded your current quota"


def extract_affected_sorries(experiment_dir: Path) -> dict:
    """
    Extract sorries that failed from an experiment.

    Includes sorries with:
    - Quota exceeded errors in failed_attempts
    - success: false

    Returns a dict with counts and the list of sorry objects.
    """
    result_file = experiment_dir / "result.json"

    if not result_file.exists():
        raise FileNotFoundError(f"result.json not found in {experiment_dir}")

    with open(result_file, "r") as f:
        results = json.load(f)

    affected_sorries = []
    quota_error_count = 0
    failed_count = 0

    for entry in results:
        failed_attempts = entry.get("failed_attempts") or []
        success = entry.get("success", True)

        # Check if any attempt had quota errors
        has_quota_error = any(
            isinstance(attempt, str) and QUOTA_ERROR_PATTERN in attempt
            for attempt in failed_attempts
        )

        # Include if quota error OR success is false
        if has_quota_error or not success:
            sorry = entry.get("sorry")
            if sorry:
                affected_sorries.append(sorry)
                if has_quota_error:
                    quota_error_count += 1
                if not success:
                    failed_count += 1

    return {
        "sorries": affected_sorries,
        "quota_error_count": quota_error_count,
        "failed_count": failed_count,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract sorries that failed (quota errors or success=false) for rerunning"
    )
    parser.add_argument(
        "experiment_dir",
        type=Path,
        help="Path to the experiment directory (containing result.json)"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output file path (default: <experiment_dir>/failed_sorries.json)"
    )

    args = parser.parse_args()

    experiment_dir = args.experiment_dir.resolve()
    result = extract_affected_sorries(experiment_dir)

    output_path = args.output or (experiment_dir / "failed_sorries.json")

    sorry_list = {
        "documentation": f"Sorries that failed (quota errors or success=false), extracted from {experiment_dir.name}",
        "sorries": result["sorries"]
    }

    with open(output_path, "w") as f:
        json.dump(sorry_list, f, indent=2)

    print(f"Extracted {len(result['sorries'])} failed sorries:")
    print(f"  - With quota errors: {result['quota_error_count']}")
    print(f"  - With success=false: {result['failed_count']}")
    print(f"Output written to: {output_path}")


if __name__ == "__main__":
    main()
