#!/usr/bin/env python3
"""
Extract snapshot mapping from experiment logs.

This script parses log files to extract the (repo, commit) -> snapshot_id mapping
that was used in the original experiment run. This allows replay runs to reuse
existing snapshots instead of rebuilding them.

Usage:
    python scripts/extract_snapshot_mapping.py <experiment_dir> [--output FILE]

Example:
    python scripts/extract_snapshot_mapping.py \
      intermediate_experiment_outputs_full_reservoir_3_months/goedel/1000/2026-01-18_18-00-23_llm \
      --output snapshot_mapping.json
"""

import argparse
import json
import re
from pathlib import Path


def extract_snapshot_from_log(log_content: str) -> str | None:
    """Extract snapshot ID from log content."""
    # Pattern: [process_single_sorry] Using snapshot: snapshot_XXXX
    match = re.search(r'\[process_single_sorry\] Using snapshot: (snapshot_\w+)', log_content)
    if match:
        return match.group(1)
    return None


def extract_repo_info_from_log(log_content: str) -> tuple[str, str] | None:
    """Extract (remote, commit) from log content."""
    # Pattern: [process_single_sorry] Repository: URL@COMMIT
    match = re.search(r'\[process_single_sorry\] Repository: (.+)@([a-f0-9]+)', log_content)
    if match:
        return (match.group(1), match.group(2))
    return None


def process_experiment_dir(experiment_dir: Path) -> dict:
    """Process all log files to extract snapshot mapping."""
    local_logs_dir = experiment_dir / 'logs' / 'process_single_sorry'

    if not local_logs_dir.exists():
        raise ValueError(f"No process_single_sorry logs found in {experiment_dir}")

    log_files = list(local_logs_dir.glob('*.log'))
    if not log_files:
        raise ValueError(f"No log files found in {local_logs_dir}")

    print(f"Found {len(log_files)} log files")

    # Build mapping: (remote, commit) -> snapshot_id
    snapshot_mapping = {}
    stats = {
        'logs_processed': 0,
        'snapshots_found': 0,
        'unique_snapshots': 0,
    }

    for log_file in log_files:
        log_content = log_file.read_text()

        snapshot_id = extract_snapshot_from_log(log_content)
        repo_info = extract_repo_info_from_log(log_content)

        if snapshot_id and repo_info:
            remote, commit = repo_info
            key = f"{remote}@{commit}"

            if key not in snapshot_mapping:
                snapshot_mapping[key] = {
                    'remote': remote,
                    'commit': commit,
                    'snapshot_id': snapshot_id,
                }
                stats['unique_snapshots'] += 1

            stats['snapshots_found'] += 1

        stats['logs_processed'] += 1

    print("\n=== Extraction Summary ===")
    print(f"Logs processed: {stats['logs_processed']}")
    print(f"Snapshots found: {stats['snapshots_found']}")
    print(f"Unique repo/commit pairs: {stats['unique_snapshots']}")

    return {
        'experiment_dir': str(experiment_dir),
        'stats': stats,
        'snapshot_mapping': snapshot_mapping,
    }


def main():
    parser = argparse.ArgumentParser(
        description='Extract snapshot mapping from experiment logs'
    )
    parser.add_argument(
        'experiment_dir',
        type=Path,
        help='Path to experiment directory containing logs/'
    )
    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=None,
        help='Output JSON file path (default: <experiment_dir>/snapshot_mapping.json)'
    )

    args = parser.parse_args()

    if not args.experiment_dir.exists():
        print(f"Error: Directory not found: {args.experiment_dir}")
        return 1

    # Extract mapping
    data = process_experiment_dir(args.experiment_dir)

    # Determine output path
    output_path = args.output
    if output_path is None:
        output_path = args.experiment_dir / 'snapshot_mapping.json'

    # Write output
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\nSaved to: {output_path}")
    return 0


if __name__ == '__main__':
    exit(main())
