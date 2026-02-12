#!/usr/bin/env python3
"""
Script to extract sorries that had TimeoutError in their failed attempts for rerunning.
"""

import argparse
import json
from pathlib import Path


TIMEOUT_ERROR_PATTERN = "EXCEPTION: TimeoutError:"


def extract_timeout_sorries(experiment_dir: Path) -> dict:
    """
    Extract sorries that had TimeoutError in their failed attempts.

    Returns a dict with counts and the list of sorry objects.
    """
    result_file = experiment_dir / "result.json"

    if not result_file.exists():
        raise FileNotFoundError(f"result.json not found in {experiment_dir}")

    with open(result_file, "r") as f:
        results = json.load(f)

    affected_sorries = []
    timeout_attempt_total = 0

    for entry in results:
        failed_attempts = entry.get("failed_attempts") or []

        # Count timeout errors in this entry
        timeout_count = sum(
            1 for attempt in failed_attempts
            if isinstance(attempt, str) and TIMEOUT_ERROR_PATTERN in attempt
        )

        if timeout_count > 0:
            sorry = entry.get("sorry")
            if sorry:
                affected_sorries.append(sorry)
                timeout_attempt_total += timeout_count

    return {
        "sorries": affected_sorries,
        "timeout_sorry_count": len(affected_sorries),
        "timeout_attempt_total": timeout_attempt_total,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract sorries that had TimeoutError in failed attempts for rerunning"
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
        help="Output file path (default: <experiment_dir>/timeout_sorries.json)"
    )

    args = parser.parse_args()

    experiment_dir = args.experiment_dir.resolve()
    result = extract_timeout_sorries(experiment_dir)

    output_path = args.output or (experiment_dir / "timeout_sorries.json")

    sorry_list = {
        "documentation": f"Sorries with TimeoutError in failed attempts, extracted from {experiment_dir.name}",
        "sorries": result["sorries"]
    }

    with open(output_path, "w") as f:
        json.dump(sorry_list, f, indent=2)

    print(f"Extracted {result['timeout_sorry_count']} sorries with TimeoutError:")
    print(f"  - Total timeout attempts across all: {result['timeout_attempt_total']}")
    print(f"Output written to: {output_path}")


if __name__ == "__main__":
    main()
