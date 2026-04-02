#!/usr/bin/env python3
"""Extract pass@k success arrays from experiment logs.

For each sorry in an experiment, extracts which of the k attempts succeeded,
producing a JSON file mapping sorry IDs to arrays of 0/1.

Can process either a single experiment directory or discover and process all
experiment subdirectories within a parent directory. Output files are
co-located with result.json files.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


def get_k_value(experiment_dir: Path) -> int:
    """Get the k value from run_summary.json."""
    run_summary_path = experiment_dir / "run_summary.json"
    if not run_summary_path.exists():
        raise FileNotFoundError(f"run_summary.json not found in {experiment_dir}")

    with open(run_summary_path) as f:
        run_summary = json.load(f)

    return run_summary["strategy"]["args"]["k"]


def find_sorry_ids(experiment_dir: Path) -> List[str]:
    """Find all sorry IDs from process_single_sorry logs."""
    logs_dir = experiment_dir / "logs" / "process_single_sorry"
    if not logs_dir.exists():
        raise FileNotFoundError(f"logs/process_single_sorry not found in {experiment_dir}")

    sorry_ids = []
    for log_file in logs_dir.glob("*.log"):
        sorry_id = log_file.stem  # Remove .log extension
        sorry_ids.append(sorry_id)

    return sorted(sorry_ids)


def get_rerun_dirs(experiment_dir: Path) -> List[Path]:
    """Get rerun directories sorted by timestamp (oldest first, most recent last).

    Args:
        experiment_dir: Path to main experiment directory

    Returns:
        List of rerun directory paths, sorted by name (timestamp)
    """
    rerun_dir = experiment_dir / "rerun"
    if not rerun_dir.exists():
        return []
    return sorted(
        [d for d in rerun_dir.iterdir() if d.is_dir()],
        key=lambda d: d.name
    )


def find_log_file(experiment_dir: Path, sorry_id: str) -> Path | None:
    """Find the log file for a sorry.

    First checks remote_morph_logs for highest-numbered attempt log.
    Falls back to process_single_sorry log which may contain embedded output.
    """
    # First try remote_morph_logs (separate downloaded logs)
    remote_logs_dir = experiment_dir / "logs" / "remote_morph_logs"
    if remote_logs_dir.exists():
        # Find all attempt files for this sorry
        pattern = f"{sorry_id}_attempt_*_run.log"
        attempt_files = list(remote_logs_dir.glob(pattern))

        if attempt_files:
            # Extract attempt numbers and find highest
            attempt_pattern = re.compile(rf"{re.escape(sorry_id)}_attempt_(\d+)_run\.log")
            max_attempt = -1
            max_file = None

            for f in attempt_files:
                match = attempt_pattern.match(f.name)
                if match:
                    attempt_num = int(match.group(1))
                    if attempt_num > max_attempt:
                        max_attempt = attempt_num
                        max_file = f

            if max_file:
                return max_file

    # Fall back to process_single_sorry log (embedded output in STDERR)
    process_logs_dir = experiment_dir / "logs" / "process_single_sorry"
    if process_logs_dir.exists():
        process_log = process_logs_dir / f"{sorry_id}.log"
        if process_log.exists():
            return process_log

    return None


def find_highest_attempt_log(experiment_dir: Path, sorry_id: str) -> Path | None:
    """Alias for find_log_file for backwards compatibility."""
    return find_log_file(experiment_dir, sorry_id)


def parse_attempt_results(log_path: Path, k: int) -> List[int]:
    """Parse log file to extract per-attempt success/failure.

    Returns array of k integers (0=failed, 1=succeeded).
    """
    results = [0] * k  # Default all to failed

    # Pattern: "Strategy LLMStrategy attempt N: verified=True/False"
    # Also handles other strategy names
    pattern = re.compile(r"Strategy \w+ attempt (\d+): verified=(True|False)")

    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                match = pattern.search(line)
                if match:
                    attempt_num = int(match.group(1))
                    verified = match.group(2) == "True"

                    # Attempt numbers are 1-indexed, convert to 0-indexed
                    if 1 <= attempt_num <= k:
                        results[attempt_num - 1] = 1 if verified else 0
    except Exception as e:
        print(f"Warning: Error reading {log_path}: {e}", file=sys.stderr)

    return results


def load_results_json(experiment_dir: Path) -> Dict[str, dict]:
    """Load results.json and index by sorry ID."""
    results_path = experiment_dir / "result.json"
    if not results_path.exists():
        return {}

    with open(results_path) as f:
        results = json.load(f)

    # Index by sorry ID
    by_id = {}
    for result in results:
        sorry_id = result.get("sorry", {}).get("id")
        if sorry_id:
            by_id[sorry_id] = result

    return by_id


def parse_verification_message(msg: str) -> Tuple[int, int] | None:
    """Parse verification message like '1 succeeded, 31 failed out of 32 attempts'.

    Returns (succeeded, failed) or None if parsing fails.
    """
    if not msg:
        return None

    pattern = re.compile(r"(\d+) succeeded, (\d+) failed")
    match = pattern.search(msg)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def verify_consistency(experiment_dir: Path, extracted_results: Dict[str, List[int]], k: int, quiet: bool = False) -> Tuple[bool, str]:
    """Verify extracted results against results.json and run_summary.json.

    Returns (passed, message) tuple.
    """
    messages = []
    all_passed = True

    # Load run_summary.json
    run_summary_path = experiment_dir / "run_summary.json"
    with open(run_summary_path) as f:
        run_summary = json.load(f)

    expected_total = run_summary["results"]["total_results"]
    expected_verified = run_summary["results"]["verified_results"]

    # Check 1: Total sorry count
    actual_total = len(extracted_results)
    if actual_total != expected_total:
        messages.append(f"Total mismatch: {actual_total} vs {expected_total}")
        all_passed = False

    # Check 2: Verified sorry count
    actual_verified = sum(1 for arr in extracted_results.values() if sum(arr) > 0)
    if actual_verified != expected_verified:
        messages.append(f"Verified mismatch: {actual_verified} vs {expected_verified}")
        all_passed = False

    # Check 3: Per-sorry consistency with results.json
    results_by_id = load_results_json(experiment_dir)
    mismatches = 0
    no_log = 0

    for sorry_id, arr in extracted_results.items():
        extracted_successes = sum(arr)

        # Check if we have a log (all zeros could mean no log or all failed)
        log_path = find_highest_attempt_log(experiment_dir, sorry_id)
        if log_path is None:
            no_log += 1
            continue

        result = results_by_id.get(sorry_id)
        if result:
            msg = result.get("verification_message", "")
            parsed = parse_verification_message(msg)
            if parsed:
                expected_successes, _ = parsed
                if extracted_successes != expected_successes:
                    mismatches += 1

    if mismatches > 0:
        messages.append(f"{mismatches} per-sorry mismatches")
        all_passed = False

    if no_log > 0:
        messages.append(f"{no_log} missing logs")

    summary = f"verified={actual_verified}/{actual_total}"
    if messages:
        summary += f" ({', '.join(messages)})"

    return all_passed, summary


def discover_experiments(parent_dir: Path) -> List[Path]:
    """
    Recursively discover all directories containing result.json and run_summary.json files
    (indicating a pass@k experiment).

    Args:
        parent_dir: Parent directory to search for experiments

    Returns:
        Sorted list of paths to experiment directories
    """
    if not parent_dir.exists():
        print(f"Error: Directory not found: {parent_dir}")
        return []

    if not parent_dir.is_dir():
        print(f"Error: Not a directory: {parent_dir}")
        return []

    # Find all directories with both result.json and run_summary.json (pass@k experiments)
    experiment_dirs = []
    for result_file in parent_dir.rglob("result.json"):
        exp_dir = result_file.parent
        run_summary = exp_dir / "run_summary.json"
        logs_dir = exp_dir / "logs" / "process_single_sorry"

        # Must have run_summary.json and logs directory to be a valid pass@k experiment
        if run_summary.exists() and logs_dir.exists():
            experiment_dirs.append(exp_dir)

    return sorted(experiment_dirs)


def should_process_experiment(experiment_dir: Path, force: bool) -> Tuple[bool, str]:
    """
    Determine if an experiment should be processed.

    Args:
        experiment_dir: Path to experiment directory
        force: Whether to force reprocessing

    Returns:
        Tuple of (should_process, reason)
    """
    output_file = experiment_dir / "pass_at_k_results.json"

    if output_file.exists() and not force:
        return False, "pass_at_k_results.json already exists (use --force to overwrite)"

    return True, "ready to process"


def process_single_experiment(experiment_dir: Path, force: bool, skip_verify: bool) -> Dict[str, Any]:
    """
    Process a single experiment directory.

    Args:
        experiment_dir: Path to experiment directory
        force: Whether to force reprocessing
        skip_verify: Whether to skip consistency verification

    Returns:
        Dictionary with processing status and details
    """
    experiment_name = experiment_dir.name
    result = {
        'experiment_name': experiment_name,
        'experiment_dir': str(experiment_dir),
        'status': 'unknown',
        'message': ''
    }

    # Check if should process
    should_process, reason = should_process_experiment(experiment_dir, force)
    if not should_process:
        result['status'] = 'skipped'
        result['message'] = reason
        return result

    try:
        # Get k value
        k = get_k_value(experiment_dir)

        # Find all sorry IDs
        sorry_ids = find_sorry_ids(experiment_dir)

        # Extract results for each sorry
        results = {}
        logs_found = 0
        logs_missing = 0

        for sorry_id in sorry_ids:
            log_path = find_highest_attempt_log(experiment_dir, sorry_id)
            if log_path:
                results[sorry_id] = parse_attempt_results(log_path, k)
                logs_found += 1
            else:
                # No log found, mark all as failed
                results[sorry_id] = [0] * k
                logs_missing += 1

        # Prepare output
        output_data = {
            "k": k,
            "results": results
        }

        # Write output
        output_path = experiment_dir / "pass_at_k_results.json"
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)

        # Verify consistency
        if not skip_verify:
            passed, verify_msg = verify_consistency(experiment_dir, results, k, quiet=True)
            if not passed:
                result['status'] = 'warning'
                result['message'] = f"k={k}, {verify_msg} (verification issues)"
            else:
                result['status'] = 'success'
                result['message'] = f"k={k}, {verify_msg}"
        else:
            verified = sum(1 for arr in results.values() if sum(arr) > 0)
            result['status'] = 'success'
            result['message'] = f"k={k}, verified={verified}/{len(results)}"

    except Exception as e:
        result['status'] = 'error'
        result['message'] = f"Error: {type(e).__name__}: {str(e)}"

    return result


def print_processing_summary(results: List[Dict[str, Any]]):
    """Print a summary of processing results."""
    print("\n" + "="*80)
    print("PROCESSING SUMMARY")
    print("="*80)

    success_count = sum(1 for r in results if r['status'] == 'success')
    warning_count = sum(1 for r in results if r['status'] == 'warning')
    skipped_count = sum(1 for r in results if r['status'] == 'skipped')
    error_count = sum(1 for r in results if r['status'] == 'error')

    print(f"Total experiments found: {len(results)}")
    print(f"  Successfully processed: {success_count}")
    print(f"  Processed with warnings: {warning_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Errors: {error_count}")
    print("")

    # Show details for each experiment
    for result in results:
        if result['status'] == 'success':
            status_symbol = "✓"
        elif result['status'] == 'warning':
            status_symbol = "⚠"
        elif result['status'] == 'skipped':
            status_symbol = "⊘"
        else:
            status_symbol = "✗"
        print(f"{status_symbol} {result['experiment_name']}: {result['message']}")

    print("="*80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description='Extract pass@k success arrays from experiment logs. '
                    'Discovers all experiment subdirectories with result.json/run_summary.json '
                    'and generates pass_at_k_results.json files co-located with the results.'
    )
    parser.add_argument(
        'parent_dir',
        type=Path,
        help='Parent directory containing experiment subdirectories '
             '(e.g., intermediate_experiment_outputs_full_reservoir_3_months)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force reprocessing even if pass_at_k_results.json already exists'
    )
    parser.add_argument(
        '--skip-verify',
        action='store_true',
        help='Skip consistency verification'
    )

    args = parser.parse_args()

    # Convert to Path
    parent_dir = args.parent_dir.resolve()

    # Discover experiments
    print(f"Discovering experiments in {parent_dir}...")
    experiment_dirs = discover_experiments(parent_dir)

    if not experiment_dirs:
        print(f"No experiment directories found in {parent_dir}")
        print("(Looking for subdirectories containing result.json, run_summary.json, and logs/process_single_sorry)")
        return

    print(f"Found {len(experiment_dirs)} experiment(s)")
    print("")

    # Process each experiment
    results = []
    for i, experiment_dir in enumerate(experiment_dirs, 1):
        print(f"[{i}/{len(experiment_dirs)}] Processing {experiment_dir.name}...")
        result = process_single_experiment(experiment_dir, args.force, args.skip_verify)
        results.append(result)

    # Print summary
    print_processing_summary(results)

    print("✓ Extraction complete!")


if __name__ == "__main__":
    main()
