#!/usr/bin/env python3
"""
Extract LLM responses from experiment logs for replay verification.

This script parses log files from a SorryDB experiment run and extracts:
1. The sorry_id from the log filename
2. The full sorry JSON from the command line
3. All LLM responses (up to k responses per sorry)

Output format:
{
  "experiment_dir": "path/to/experiment",
  "sorry_responses": {
    "sorry_id_1": {
      "sorry_json": { ... },
      "llm_responses": ["response_1", "response_2", ...]
    },
    ...
  }
}

Usage:
    python scripts/extract_llm_responses_for_replay.py <experiment_dir> [--output FILE]

Example:
    python scripts/extract_llm_responses_for_replay.py \
      intermediate_experiment_outputs_full_reservoir_3_months/goedel/1000/2026-01-18_18-00-23_llm \
      --output llm_responses_for_replay.json
"""

import argparse
import json
import re
from pathlib import Path


def extract_sorry_json_from_command(log_content: str) -> dict | None:
    """Extract the sorry JSON from the 'Full command:' line in the log."""
    # Pattern: --sorry-json {JSON} --agent-strategy
    # The JSON is not quoted, so we need to find its boundaries
    match = re.search(r'--sorry-json\s+(\{.+?\})\s+--agent-strategy', log_content)
    if match:
        json_str = match.group(1)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"Warning: Failed to parse sorry JSON: {e}")
            return None
    return None


def extract_llm_responses_from_log(log_content: str) -> list[str]:
    """Extract all LLM responses from a log file.

    Responses are delimited by:
    - Start: '[INFO] Full LLM response:\n'
    - End: Next log line starting with '[YYYY-MM-DD HH:MM:SS]'
    """
    responses = []

    # Pattern to find "Full LLM response:" lines
    response_starts = list(re.finditer(r'\[INFO\] Full LLM response:\n', log_content))

    # Pattern to find log line timestamps
    log_line_pattern = r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]'

    for match in response_starts:
        start_pos = match.end()

        # Find where this response ends (next log line)
        next_log = re.search(log_line_pattern, log_content[start_pos:])
        if next_log:
            end_pos = start_pos + next_log.start()
        else:
            end_pos = len(log_content)

        response_text = log_content[start_pos:end_pos].rstrip()
        if response_text:  # Only add non-empty responses
            responses.append(response_text)

    return responses


def extract_sorry_id_from_filename(filename: str) -> str | None:
    """Extract sorry_id from log filename.

    Supports two patterns:
    - '{sorry_id}_attempt_N_run.log' (remote_morph_logs)
    - '{sorry_id}.log' (process_single_sorry)
    """
    # Try remote_morph_logs pattern first
    match = re.match(r'^([a-f0-9]{64})_attempt_\d+_run\.log$', filename)
    if match:
        return match.group(1)

    # Try process_single_sorry pattern
    match = re.match(r'^([a-f0-9]{64})\.log$', filename)
    if match:
        return match.group(1)

    return None


def process_experiment_dir(experiment_dir: Path) -> dict:
    """Process all log files in an experiment directory.

    Checks both remote_morph_logs and process_single_sorry directories:
    - remote_morph_logs: Primary source, contains logs downloaded from MorphCloud instances
    - process_single_sorry: Fallback, may contain LLM responses if remote log download failed
      but the command output was captured via stdout

    For each sorry, uses remote_morph_logs if available, otherwise falls back to process_single_sorry.
    """
    remote_logs_dir = experiment_dir / 'logs' / 'remote_morph_logs'
    local_logs_dir = experiment_dir / 'logs' / 'process_single_sorry'

    # Collect logs from both directories
    remote_logs = list(remote_logs_dir.glob('*.log')) if remote_logs_dir.exists() else []
    local_logs = list(local_logs_dir.glob('*.log')) if local_logs_dir.exists() else []

    if not remote_logs and not local_logs:
        raise ValueError(f"No log files found in {experiment_dir}/logs/")

    # Build a mapping of sorry_id -> log files, preferring remote_morph_logs
    sorry_to_logs: dict[str, list[Path]] = {}

    # First, add remote logs (these take priority)
    for log_file in remote_logs:
        sorry_id = extract_sorry_id_from_filename(log_file.name)
        if sorry_id:
            if sorry_id not in sorry_to_logs:
                sorry_to_logs[sorry_id] = []
            sorry_to_logs[sorry_id].append(log_file)

    # Then, add local logs only for sorries not already covered by remote logs
    for log_file in local_logs:
        sorry_id = extract_sorry_id_from_filename(log_file.name)
        if sorry_id and sorry_id not in sorry_to_logs:
            sorry_to_logs[sorry_id] = [log_file]

    # Flatten to list of all log files to process
    log_files = [log for logs in sorry_to_logs.values() for log in logs]

    print(f"Found {len(remote_logs)} remote logs, {len(local_logs)} local logs")
    print(f"Processing {len(sorry_to_logs)} unique sorries from {len(log_files)} log files")

    print(f"Found {len(log_files)} log files")

    sorry_responses = {}
    stats = {
        'total_logs': len(log_files),
        'total_responses': 0,
        'sorries_processed': 0,
        'parse_failures': 0,
    }

    for log_file in log_files:
        sorry_id = extract_sorry_id_from_filename(log_file.name)
        if not sorry_id:
            print(f"Warning: Could not extract sorry_id from {log_file.name}")
            stats['parse_failures'] += 1
            continue

        log_content = log_file.read_text()

        # Extract sorry JSON (only once per sorry)
        sorry_json = None
        if sorry_id not in sorry_responses:
            sorry_json = extract_sorry_json_from_command(log_content)
            if sorry_json is None:
                print(f"Warning: Could not extract sorry JSON from {log_file.name}")
                stats['parse_failures'] += 1

        # Extract LLM responses
        responses = extract_llm_responses_from_log(log_content)

        if sorry_id in sorry_responses:
            # Append responses if this sorry was already seen (multiple attempt files)
            sorry_responses[sorry_id]['llm_responses'].extend(responses)
        else:
            sorry_responses[sorry_id] = {
                'sorry_json': sorry_json,
                'llm_responses': responses,
            }
            stats['sorries_processed'] += 1

        stats['total_responses'] += len(responses)

    # Print summary
    print("\n=== Extraction Summary ===")
    print(f"Log files processed: {stats['total_logs']}")
    print(f"Sorries extracted: {stats['sorries_processed']}")
    print(f"Total LLM responses: {stats['total_responses']}")
    print(f"Parse failures: {stats['parse_failures']}")

    # Calculate response distribution
    response_counts = [len(s['llm_responses']) for s in sorry_responses.values()]
    if response_counts:
        avg_responses = sum(response_counts) / len(response_counts)
        print(f"Average responses per sorry: {avg_responses:.1f}")
        print(f"Min/Max responses: {min(response_counts)}/{max(response_counts)}")

    return {
        'experiment_dir': str(experiment_dir),
        'stats': stats,
        'sorry_responses': sorry_responses,
    }


def main():
    parser = argparse.ArgumentParser(
        description='Extract LLM responses from experiment logs for replay verification'
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
        help='Output JSON file path (default: <experiment_dir>/llm_responses_for_replay.json)'
    )

    args = parser.parse_args()

    if not args.experiment_dir.exists():
        print(f"Error: Directory not found: {args.experiment_dir}")
        return 1

    # Extract responses
    data = process_experiment_dir(args.experiment_dir)

    # Determine output path
    output_path = args.output
    if output_path is None:
        output_path = args.experiment_dir / 'llm_responses_for_replay.json'

    # Write output
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\nSaved to: {output_path}")
    return 0


if __name__ == '__main__':
    exit(main())
