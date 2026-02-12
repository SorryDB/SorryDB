#!/usr/bin/env python3
"""
Script to extract sorries where success=false for rerunning.
"""

import argparse
import json
from pathlib import Path


def extract_failed_sorries(experiment_dir: Path) -> dict:
    """
    Extract sorries where success=false.

    Returns a dict with count and the list of sorry objects.
    """
    result_file = experiment_dir / "result.json"

    if not result_file.exists():
        raise FileNotFoundError(f"result.json not found in {experiment_dir}")

    with open(result_file, "r") as f:
        results = json.load(f)

    failed_sorries = []

    for entry in results:
        success = entry.get("success", True)

        if not success:
            sorry = entry.get("sorry")
            if sorry:
                failed_sorries.append(sorry)

    return {
        "sorries": failed_sorries,
        "failed_count": len(failed_sorries),
        "total_count": len(results),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract sorries where success=false for rerunning"
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
    result = extract_failed_sorries(experiment_dir)

    output_path = args.output or (experiment_dir / "failed_sorries.json")

    sorry_list = {
        "documentation": f"Sorries with success=false, extracted from {experiment_dir.name}",
        "sorries": result["sorries"]
    }

    with open(output_path, "w") as f:
        json.dump(sorry_list, f, indent=2)

    print(f"Extracted {result['failed_count']} failed sorries (out of {result['total_count']} total)")
    print(f"Output written to: {output_path}")


if __name__ == "__main__":
    main()
