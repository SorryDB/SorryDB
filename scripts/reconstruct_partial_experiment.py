#!/usr/bin/env python3
"""
Reconstruct result.json and run_summary.json from a partially completed experiment.

This script combines individual result files into the final result.json format,
and generates a run_summary.json with accurate statistics.

Usage:
    python scripts/reconstruct_partial_experiment.py \
        --experiment-dir intermediate_experiment_outputs_full_reservoir_3_months/gpt/1000/2026-01-23_02-33-21_llm \
        --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json \
        --strategy '{"name":"llm","args":{"k":32,"model_config":{"provider":"openai","params":{"model":"gpt-5.2"}}}}'
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from git import Repo


def load_input_sorries(sorry_file: Path) -> dict[str, dict]:
    """Load sorries from input file, returning dict mapping ID to sorry."""
    with open(sorry_file, "r") as f:
        data = json.load(f)

    # Handle both list format and dict with "sorries" key
    if isinstance(data, list):
        sorries = data
    elif isinstance(data, dict) and "sorries" in data:
        sorries = data["sorries"]
    else:
        raise ValueError(f"Unexpected format in {sorry_file}")

    return {s["id"]: s for s in sorries}


def load_individual_results(individual_dir: Path) -> tuple[list[dict], list[str]]:
    """Load all individual result files from the individual/ directory.

    Returns:
        Tuple of (results list, list of sorry IDs with empty/invalid files)
    """
    results = []
    empty_file_ids = []

    for file_path in individual_dir.glob("*.json"):
        # Extract sorry ID from filename (filename is {sorry_id}.json)
        sorry_id = file_path.stem

        # Check for empty files
        if file_path.stat().st_size == 0:
            print(f"  Warning: Empty file {file_path.name}, will mark as error")
            empty_file_ids.append(sorry_id)
            continue

        try:
            with open(file_path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"  Warning: Invalid JSON in {file_path.name}: {e}, will mark as error")
            empty_file_ids.append(sorry_id)
            continue

        # Individual files can contain a single result dict or a list of results
        if isinstance(data, dict):
            results.append(data)
        elif isinstance(data, list):
            results.extend(data)

    return results, empty_file_ids


def load_failed_sorries(failed_path: Path) -> set[str]:
    """Load sorry IDs from failed.json (build failures)."""
    if not failed_path.exists():
        return set()

    with open(failed_path, "r") as f:
        data = json.load(f)

    return {entry["sorry"]["id"] for entry in data}


def create_error_result(sorry: dict, strategy_name: str) -> dict:
    """Create an error result entry for a sorry that wasn't processed."""
    return {
        "sorry": sorry,
        "proof": None,
        "proof_verified": False,
        "feedback": None,
        "verification_message": "Experiment was interrupted before this sorry could be processed",
        "success": False,
        "error_type": "experiment_interrupted",
        "error_message": "Experiment was interrupted before this sorry could be processed",
        "strategy_name": strategy_name,
        "failed_attempts": [],
        "successful_attempts": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost": 0.0,
    }


def calculate_sorry_stats(results: list[dict]) -> dict:
    """Calculate stats grouped by unique sorry ID."""
    by_sorry = defaultdict(list)
    for r in results:
        sorry = r.get("sorry")
        if sorry:
            sorry_id = sorry.get("id") if isinstance(sorry, dict) else getattr(sorry, "id", None)
            if sorry_id:
                by_sorry[sorry_id].append(r)

    unique_sorries = len(by_sorry)
    unique_verified = sum(
        1 for sorry_results in by_sorry.values() if any(r.get("proof_verified", False) for r in sorry_results)
    )
    unique_failed = sum(1 for sorry_results in by_sorry.values() if not any(r.get("success", False) for r in sorry_results))

    return {
        "unique_sorries": unique_sorries,
        "unique_verified": unique_verified,
        "unique_failed": unique_failed,
        "total_results": len(results),
        "verified_results": sum(1 for r in results if r.get("proof_verified", False)),
    }


def get_git_info() -> dict:
    """Get SorryDB git commit info."""
    try:
        git_repo = Repo(".")
        return {
            "branch": git_repo.active_branch.name,
            "commit": git_repo.head.commit.hexsha,
            "commit_short": git_repo.head.commit.hexsha[:12],
            "commit_message": git_repo.head.commit.message.strip(),
            "is_dirty": git_repo.is_dirty(),
        }
    except Exception as e:
        return {
            "branch": "unknown",
            "commit": "unknown",
            "commit_short": "unknown",
            "commit_message": f"Error getting commit info: {e}",
            "is_dirty": None,
        }


def infer_timestamps(experiment_dir: Path) -> tuple[datetime, datetime]:
    """Infer start and end timestamps from directory name and file modification times."""
    # Try to parse start time from directory name (format: YYYY-MM-DD_HH-MM-SS_strategy)
    dir_name = experiment_dir.name
    try:
        timestamp_str = "_".join(dir_name.split("_")[:2])  # "2026-01-23_02-33-21"
        start_time = datetime.strptime(timestamp_str, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        start_time = datetime.now()

    # Use latest file modification time as end time
    individual_dir = experiment_dir / "individual"
    if individual_dir.exists():
        latest_mtime = max(
            (f.stat().st_mtime for f in individual_dir.glob("*.json")),
            default=start_time.timestamp(),
        )
        end_time = datetime.fromtimestamp(latest_mtime)
    else:
        end_time = datetime.now()

    return start_time, end_time


def create_run_summary(
    sorry_json_path: Path,
    strategy_name: str,
    strategy_args: dict,
    start_time: datetime,
    end_time: datetime,
    total_sorries: int,
    prepared_sorries: int,
    failed_builds: int,
    stats: dict,
    results: list[dict],
    max_workers: int = 25,
) -> dict:
    """Create a summary dictionary for the run with metadata."""
    duration_seconds = (end_time - start_time).total_seconds()

    summary = {
        "run_metadata": {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration_seconds,
            "duration_human": f"{int(duration_seconds // 60)}m {int(duration_seconds % 60)}s",
        },
        "sorrydb_info": get_git_info(),
        "input": {
            "sorry_json_path": str(sorry_json_path),
            "sorry_json_filename": sorry_json_path.name,
        },
        "strategy": {
            "name": strategy_name,
            "args": strategy_args,
        },
        "execution": {
            "max_workers": max_workers,
        },
        "results": {
            "total_sorries_loaded": total_sorries,
            "prepared_sorries": prepared_sorries,
            "failed_builds": failed_builds,
            "unique_sorries_processed": stats["unique_sorries"],
            "unique_sorries_verified": stats["unique_verified"],
            "failed_processing": stats["unique_failed"],
            "total_results": stats["total_results"],
            "verified_results": stats["verified_results"],
        },
    }

    # Aggregate costs from results
    total_input_tokens = sum(r.get("input_tokens", 0) or 0 for r in results)
    total_output_tokens = sum(r.get("output_tokens", 0) or 0 for r in results)
    total_cost = sum(r.get("estimated_cost", 0) or 0 for r in results)

    summary["cost"] = {
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cost_usd": round(total_cost, 4),
    }

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Reconstruct result.json and run_summary.json from a partial experiment"
    )
    parser.add_argument(
        "--experiment-dir",
        type=str,
        required=True,
        help="Path to the experiment directory containing individual/ and failed.json",
    )
    parser.add_argument(
        "--sorry-file",
        type=str,
        required=True,
        help="Path to the original sorry JSON file used as input",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        required=True,
        help="JSON string of the strategy spec (e.g., '{\"name\":\"llm\",\"args\":{...}}')",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=25,
        help="Max workers used in the run (default: 25)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without writing files",
    )

    args = parser.parse_args()

    experiment_dir = Path(args.experiment_dir)
    sorry_file = Path(args.sorry_file)
    strategy_spec = json.loads(args.strategy)
    strategy_name = strategy_spec.get("name", "unknown")
    strategy_args = strategy_spec.get("args", {})

    # Validate paths
    if not experiment_dir.exists():
        print(f"Error: Experiment directory does not exist: {experiment_dir}")
        return 1

    if not sorry_file.exists():
        print(f"Error: Sorry file does not exist: {sorry_file}")
        return 1

    individual_dir = experiment_dir / "individual"
    if not individual_dir.exists():
        print(f"Error: Individual results directory does not exist: {individual_dir}")
        return 1

    # Load data
    print(f"Loading input sorries from {sorry_file}...")
    input_sorries = load_input_sorries(sorry_file)
    print(f"  Loaded {len(input_sorries)} sorries")

    print(f"Loading individual results from {individual_dir}...")
    individual_results, empty_file_ids = load_individual_results(individual_dir)
    print(f"  Loaded {len(individual_results)} results")
    if empty_file_ids:
        print(f"  Found {len(empty_file_ids)} empty/invalid files")

    failed_path = experiment_dir / "failed.json"
    print(f"Loading build failures from {failed_path}...")
    failed_ids = load_failed_sorries(failed_path)
    print(f"  Loaded {len(failed_ids)} build failures")

    # Identify processed and missing sorries
    processed_ids = {r["sorry"]["id"] for r in individual_results if r.get("sorry")}
    all_handled_ids = processed_ids | failed_ids
    # Also mark sorries with empty/invalid files as missing
    missing_ids = (set(input_sorries.keys()) - all_handled_ids) | set(empty_file_ids)

    print("\nSummary:")
    print(f"  Total input sorries: {len(input_sorries)}")
    print(f"  Successfully processed: {len(processed_ids)}")
    print(f"  Build failures: {len(failed_ids)}")
    print(f"  Missing (to be marked as errors): {len(missing_ids)}")

    # Create error entries for missing sorries
    print(f"\nCreating error entries for {len(missing_ids)} missing sorries...")
    error_results = [
        create_error_result(input_sorries[sorry_id], strategy_name)
        for sorry_id in missing_ids
    ]

    # Combine all results
    all_results = individual_results + error_results
    print(f"Total results for result.json: {len(all_results)}")

    # Calculate stats
    stats = calculate_sorry_stats(all_results)
    print("\nStats:")
    print(f"  Unique sorries processed: {stats['unique_sorries']}")
    print(f"  Unique sorries verified: {stats['unique_verified']}")
    print(f"  Unique sorries failed: {stats['unique_failed']}")
    print(f"  Total results: {stats['total_results']}")
    print(f"  Verified results: {stats['verified_results']}")

    # Infer timestamps
    start_time, end_time = infer_timestamps(experiment_dir)
    print("\nInferred timestamps:")
    print(f"  Start: {start_time.isoformat()}")
    print(f"  End: {end_time.isoformat()}")

    # Create run summary
    run_summary = create_run_summary(
        sorry_json_path=sorry_file,
        strategy_name=strategy_name,
        strategy_args=strategy_args,
        start_time=start_time,
        end_time=end_time,
        total_sorries=len(input_sorries),
        prepared_sorries=len(input_sorries) - len(failed_ids),
        failed_builds=len(failed_ids),
        stats=stats,
        results=all_results,
        max_workers=args.max_workers,
    )

    if args.dry_run:
        print("\n[DRY RUN] Would write the following files:")
        print(f"  - {experiment_dir / 'result.json'} ({len(all_results)} entries)")
        print(f"  - {experiment_dir / 'run_summary.json'}")
        print("\nRun summary preview:")
        print(json.dumps(run_summary, indent=2))
        return 0

    # Write result.json
    result_path = experiment_dir / "result.json"
    print(f"\nWriting {result_path}...")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=4, ensure_ascii=False)
    print(f"  Written {len(all_results)} results")

    # Write run_summary.json
    summary_path = experiment_dir / "run_summary.json"
    print(f"Writing {summary_path}...")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(run_summary, f, indent=4, ensure_ascii=False)
    print("  Done")

    print("\nReconstruction complete!")
    return 0


if __name__ == "__main__":
    exit(main())
