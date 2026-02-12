#!/usr/bin/env python3
"""Count sorries that have TimeoutError in their failed attempts."""

import json
import sys
from pathlib import Path


def count_timeout_errors(result_file: Path) -> None:
    with open(result_file) as f:
        results = json.load(f)

    total_sorries = len(results)
    sorries_with_timeout = 0
    total_timeout_attempts = 0

    for result in results:
        failed_attempts = result.get("failed_attempts", []) or []
        timeout_count = sum(
            1 for attempt in failed_attempts
            if isinstance(attempt, str) and "EXCEPTION: TimeoutError:" in attempt
        )
        if timeout_count > 0:
            sorries_with_timeout += 1
            total_timeout_attempts += timeout_count

    print(f"Total sorries: {total_sorries}")
    print(f"Sorries with at least one TimeoutError: {sorries_with_timeout}")
    print(f"Percentage: {sorries_with_timeout / total_sorries * 100:.1f}%")
    print(f"Total timeout attempts across all sorries: {total_timeout_attempts}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        result_file = Path(
            "intermediate_experiment_outputs_full_reservoir_3_months/kimina/2026-01-23_17-11-16_llm/result.json"
        )
    else:
        result_file = Path(sys.argv[1])

    count_timeout_errors(result_file)
