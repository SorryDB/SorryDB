#!/usr/bin/env python3
"""Extract iteration success data from agentic experiment logs.

For each sorry in an agentic experiment, extracts which iteration (if any)
successfully proved the sorry. Produces a JSON file mapping sorry IDs to
iteration numbers (or null if not solved).

Can process either a single experiment directory or discover and process all
agentic experiment subdirectories within a parent directory. Output files are
co-located with result.json files.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def get_max_iterations(experiment_dir: Path) -> int:
    """Get the max_iterations value from run_summary.json."""
    run_summary_path = experiment_dir / "run_summary.json"
    if not run_summary_path.exists():
        raise FileNotFoundError(f"run_summary.json not found in {experiment_dir}")

    with open(run_summary_path) as f:
        run_summary = json.load(f)

    return run_summary["strategy"]["args"]["max_iterations"]


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


def find_log_file(experiment_dir: Path, sorry_id: str) -> Optional[Path]:
    """Find the log file for a sorry.

    First checks remote_morph_logs for attempt log files.
    Falls back to process_single_sorry log which may contain embedded output.
    """
    # First try remote_morph_logs (separate downloaded logs)
    remote_logs_dir = experiment_dir / "logs" / "remote_morph_logs"
    if remote_logs_dir.exists():
        # Find all attempt files for this sorry
        pattern = f"{sorry_id}_attempt_*_run.log"
        attempt_files = list(remote_logs_dir.glob(pattern))

        if attempt_files:
            # For agentic, we typically only have attempt_1, but handle multiple
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


def parse_success_iteration(log_path: Path) -> Optional[int]:
    """Parse log file to find which iteration succeeded.

    Returns the iteration number (1-indexed) or None if no success found.
    """
    # Pattern: "[Iteration N] ✓ Proof verified successfully!"
    pattern = re.compile(r"\[Iteration (\d+)\] ✓ Proof verified successfully!")

    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                match = pattern.search(line)
                if match:
                    return int(match.group(1))
    except Exception as e:
        print(f"Warning: Error reading {log_path}: {e}", file=sys.stderr)

    return None


def is_sorry_verified(experiment_dir: Path, sorry_id: str) -> bool:
    """Check if a sorry is marked as verified in its individual JSON file.

    Reads individual/{sorry_id}.json and checks if proof_verified is true.
    """
    individual_path = experiment_dir / "individual" / f"{sorry_id}.json"
    if not individual_path.exists():
        return False

    try:
        with open(individual_path) as f:
            data = json.load(f)
        # The file contains a list with one result object
        if isinstance(data, list) and len(data) > 0:
            return data[0].get("proof_verified", False) is True
        return False
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"Warning: Error reading {individual_path}: {e}", file=sys.stderr)
        return False


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


def verify_consistency(
    experiment_dir: Path,
    extracted_results: Dict[str, Optional[int]],
    quiet: bool = False
) -> Tuple[bool, str]:
    """Verify extracted results against run_summary.json.

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
    actual_verified = sum(1 for v in extracted_results.values() if v is not None)
    if actual_verified != expected_verified:
        messages.append(f"Verified mismatch: {actual_verified} vs {expected_verified}")
        all_passed = False

    summary = f"verified={actual_verified}/{actual_total}"
    if messages:
        summary += f" ({', '.join(messages)})"

    return all_passed, summary


def discover_experiments(parent_dir: Path) -> List[Path]:
    """
    Recursively discover all agentic experiment directories.

    Looks for directories containing result.json, run_summary.json with
    strategy.name == "agentic", and logs/process_single_sorry.

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

    experiment_dirs = []
    for result_file in parent_dir.rglob("result.json"):
        exp_dir = result_file.parent
        run_summary_path = exp_dir / "run_summary.json"
        logs_dir = exp_dir / "logs" / "process_single_sorry"

        # Must have run_summary.json and logs directory
        if not run_summary_path.exists() or not logs_dir.exists():
            continue

        # Check if this is an agentic experiment
        try:
            with open(run_summary_path) as f:
                run_summary = json.load(f)
            strategy_name = run_summary.get("strategy", {}).get("name", "")
            if strategy_name != "agentic":
                continue
            # Also verify max_iterations exists
            if "max_iterations" not in run_summary.get("strategy", {}).get("args", {}):
                continue
        except (json.JSONDecodeError, KeyError):
            continue

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
    output_file = experiment_dir / "agentic_iterations.json"

    if output_file.exists() and not force:
        return False, "agentic_iterations.json already exists (use --force to overwrite)"

    return True, "ready to process"


def process_single_experiment(
    experiment_dir: Path,
    force: bool,
    skip_verify: bool
) -> Dict[str, Any]:
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
        # Get max_iterations value
        max_iterations = get_max_iterations(experiment_dir)

        # Find all sorry IDs
        sorry_ids = find_sorry_ids(experiment_dir)

        # Extract results for each sorry
        results: Dict[str, Optional[int]] = {}
        logs_found = 0
        logs_missing = 0

        for sorry_id in sorry_ids:
            # First check if the sorry is actually verified in the individual result
            if not is_sorry_verified(experiment_dir, sorry_id):
                # Not verified in individual JSON, mark as not solved
                results[sorry_id] = None
                continue

            log_path = find_log_file(experiment_dir, sorry_id)
            if log_path:
                iteration = parse_success_iteration(log_path)
                results[sorry_id] = iteration
                logs_found += 1
            else:
                # No log found but verified - this shouldn't happen, mark as not solved
                results[sorry_id] = None
                logs_missing += 1

        # Prepare output
        output_data = {
            "max_iterations": max_iterations,
            "results": results
        }

        # Write output
        output_path = experiment_dir / "agentic_iterations.json"
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)

        # Verify consistency
        if not skip_verify:
            passed, verify_msg = verify_consistency(experiment_dir, results, quiet=True)
            if not passed:
                result['status'] = 'warning'
                result['message'] = f"max_iterations={max_iterations}, {verify_msg} (verification issues)"
            else:
                result['status'] = 'success'
                result['message'] = f"max_iterations={max_iterations}, {verify_msg}"
        else:
            verified = sum(1 for v in results.values() if v is not None)
            result['status'] = 'success'
            result['message'] = f"max_iterations={max_iterations}, verified={verified}/{len(results)}"

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
        description='Extract agentic iteration success data from experiment logs. '
                    'Discovers all agentic experiment subdirectories with result.json/run_summary.json '
                    'and generates agentic_iterations.json files co-located with the results.'
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
        help='Force reprocessing even if agentic_iterations.json already exists'
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
    print(f"Discovering agentic experiments in {parent_dir}...")
    experiment_dirs = discover_experiments(parent_dir)

    if not experiment_dirs:
        print(f"No agentic experiment directories found in {parent_dir}")
        print("(Looking for subdirectories containing result.json, run_summary.json with strategy.name='agentic', and logs/process_single_sorry)")
        return

    print(f"Found {len(experiment_dirs)} agentic experiment(s)")
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
