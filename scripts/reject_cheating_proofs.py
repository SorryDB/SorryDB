#!/usr/bin/env python3
"""
Reject cheating proofs (e.g., sorryAx, sorry) from experiment results.

A proof using `sorryAx` or `sorry` doesn't actually prove anything - these
are placeholders that skip the proof obligation. This script corrects
experiment results by treating such proofs as failed verifications.

Usage:
    python scripts/reject_cheating_proofs.py <experiment_dir> [--dry-run] [--run-analysis] [-v]

Example:
    python scripts/reject_cheating_proofs.py outputs/debug_agentic/2026-01-23_14-32-25_agentic --dry-run
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

# Patterns to detect cheating proofs
PATTERN_SORRY_AX = re.compile(r'\bsorryAx\b', re.IGNORECASE)
PATTERN_SORRY = re.compile(r'\bsorry\b', re.IGNORECASE)


def get_cheating_patterns(just_sorry_ax: bool = False) -> List[re.Pattern]:
    """Get the list of cheating patterns based on configuration."""
    if just_sorry_ax:
        return [PATTERN_SORRY_AX]
    return [PATTERN_SORRY_AX, PATTERN_SORRY]


def is_cheating_proof(proof: Optional[str], patterns: List[re.Pattern]) -> bool:
    """Check if a proof contains any of the given cheating patterns."""
    if proof is None:
        return False
    return any(pattern.search(proof) for pattern in patterns)


def get_cheat_type(proof: str) -> str:
    """Determine the type of cheating in a proof (sorryAx or sorry)."""
    if PATTERN_SORRY_AX.search(proof):
        return "sorryAx"
    elif PATTERN_SORRY.search(proof):
        return "sorry"
    return "unknown"


def correct_entry(entry: dict, patterns: List[re.Pattern]) -> Tuple[dict, int, List[dict]]:
    """
    Correct a single SorryResult entry by rejecting cheating proofs.

    Args:
        entry: A SorryResult dictionary
        patterns: List of regex patterns to detect cheating proofs

    Returns:
        Tuple of (modified_entry, rejected_count, rejected_proofs)
        where rejected_proofs is a list of dicts with 'proof' and 'cheat_type' keys
    """
    rejected_proofs: List[dict] = []

    # Get current attempts
    successful = entry.get('successful_attempts') or []
    failed = entry.get('failed_attempts') or []

    # Separate cheating from valid proofs
    valid_proofs = []
    for proof in successful:
        if is_cheating_proof(proof, patterns):
            rejected_proofs.append({
                'proof': proof,
                'cheat_type': get_cheat_type(proof)
            })
            failed.append(proof)
        else:
            valid_proofs.append(proof)

    if not rejected_proofs:
        return entry, 0, []

    # Update entry
    entry['successful_attempts'] = valid_proofs if valid_proofs else None
    entry['failed_attempts'] = failed if failed else None

    # Update proof field if it was a cheating proof
    current_proof = entry.get('proof')
    if current_proof and is_cheating_proof(current_proof, patterns):
        entry['proof'] = valid_proofs[0] if valid_proofs else None

    # Update proof_verified
    entry['proof_verified'] = len(valid_proofs) > 0

    # Update verification_message
    total_attempts = len(valid_proofs) + len(failed)
    entry['verification_message'] = f"{len(valid_proofs)} succeeded, {len(failed)} failed out of {total_attempts} attempts"

    return entry, len(rejected_proofs), rejected_proofs


def backup_file(path: Path, backup_dir: Path) -> Path:
    """Create a backup of a file in the backup directory."""
    backup_path = backup_dir / path.name
    shutil.copy2(path, backup_path)
    return backup_path


def process_result_json(path: Path, patterns: List[re.Pattern], dry_run: bool = False) -> dict:
    """
    Process result.json and return correction statistics.

    Args:
        path: Path to result.json
        patterns: List of regex patterns to detect cheating proofs
        dry_run: If True, don't modify the file

    Returns:
        Statistics dictionary
    """
    with open(path, 'r') as f:
        data = json.load(f)

    stats = {
        'total_entries': len(data),
        'entries_corrected': 0,
        'proofs_rejected': 0,
        'verified_lost': 0,
        'rejected_details': [],
        'sorry_ax_count': 0,
        'sorry_count': 0,
    }

    for entry in data:
        was_verified = entry.get('proof_verified', False)
        entry, rejected_count, rejected_proofs = correct_entry(entry, patterns)

        if rejected_count > 0:
            stats['entries_corrected'] += 1
            stats['proofs_rejected'] += rejected_count

            # Count by cheat type
            for rp in rejected_proofs:
                if rp['cheat_type'] == 'sorryAx':
                    stats['sorry_ax_count'] += 1
                elif rp['cheat_type'] == 'sorry':
                    stats['sorry_count'] += 1

            if was_verified and not entry.get('proof_verified', False):
                stats['verified_lost'] += 1

            sorry_id = entry.get('sorry', {}).get('id', 'unknown')
            stats['rejected_details'].append({
                'sorry_id': sorry_id,
                'rejected_proofs': rejected_proofs,
                'still_verified': entry.get('proof_verified', False)
            })

    if not dry_run and stats['entries_corrected'] > 0:
        with open(path, 'w') as f:
            json.dump(data, f, indent=4)

    return stats


def update_run_summary(path: Path, verified_lost: int, dry_run: bool = False) -> None:
    """Update run_summary.json with corrected counts."""
    with open(path, 'r') as f:
        data = json.load(f)

    if 'results' in data:
        results = data['results']
        if 'unique_sorries_verified' in results:
            results['unique_sorries_verified'] = max(0, results['unique_sorries_verified'] - verified_lost)
        if 'verified_results' in results:
            results['verified_results'] = max(0, results['verified_results'] - verified_lost)
        if 'verified_sorries' in results:
            results['verified_sorries'] = max(0, results['verified_sorries'] - verified_lost)

    if not dry_run:
        with open(path, 'w') as f:
            json.dump(data, f, indent=4)


def process_individual_files(individual_dir: Path, affected_sorry_ids: set, patterns: List[re.Pattern], dry_run: bool = False) -> int:
    """
    Process individual JSON files for affected sorries.

    Args:
        individual_dir: Path to individual/ directory
        affected_sorry_ids: Set of sorry IDs that need correction
        patterns: List of regex patterns to detect cheating proofs
        dry_run: If True, don't modify files

    Returns:
        Number of files updated
    """
    updated = 0

    for sorry_id in affected_sorry_ids:
        individual_file = individual_dir / f"{sorry_id}.json"
        if individual_file.exists():
            with open(individual_file, 'r') as f:
                data = json.load(f)

            # Individual files contain an array with typically one entry
            modified = False
            for entry in data:
                entry, rejected_count, _ = correct_entry(entry, patterns)
                if rejected_count > 0:
                    modified = True

            if modified and not dry_run:
                with open(individual_file, 'w') as f:
                    json.dump(data, f, indent=2)
                updated += 1

    return updated


def process_experiment(experiment_dir: Path, patterns: List[re.Pattern], dry_run: bool = False, run_analysis: bool = False) -> dict:
    """
    Process an entire experiment directory.

    Args:
        experiment_dir: Path to experiment directory
        patterns: List of regex patterns to detect cheating proofs
        dry_run: If True, don't modify files
        run_analysis: If True, regenerate analysis.json after correction

    Returns:
        Statistics dictionary
    """
    result_json = experiment_dir / "result.json"
    run_summary = experiment_dir / "run_summary.json"
    individual_dir = experiment_dir / "individual"

    if not result_json.exists():
        return {'error': 'result.json not found'}

    # Create backup directory
    backup_dir = None
    if not dry_run:
        backup_dir = experiment_dir / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(exist_ok=True)
        backup_file(result_json, backup_dir)
        if run_summary.exists():
            backup_file(run_summary, backup_dir)

    # Process result.json
    stats = process_result_json(result_json, patterns, dry_run)
    stats['backup_dir'] = str(backup_dir) if backup_dir else None

    # Update run_summary.json
    if run_summary.exists() and stats['verified_lost'] > 0:
        update_run_summary(run_summary, stats['verified_lost'], dry_run)

    # Update individual files
    if individual_dir.exists() and stats['rejected_details']:
        affected_ids = {d['sorry_id'] for d in stats['rejected_details']}
        stats['individual_files_updated'] = process_individual_files(
            individual_dir, affected_ids, patterns, dry_run
        )
    else:
        stats['individual_files_updated'] = 0

    # Optionally regenerate analysis
    if run_analysis and not dry_run and stats['entries_corrected'] > 0:
        import subprocess
        analysis_script = Path(__file__).parent.parent / "intermediate_experiment_outputs" / "analyze_proof_verification.py"
        if analysis_script.exists():
            print("\nRegenerating analysis.json...")
            subprocess.run([
                sys.executable, str(analysis_script), str(experiment_dir), '--force'
            ])

    return stats


def print_report(stats: dict, verbose: bool, dry_run: bool, experiment_dir: Path) -> None:
    """Print a formatted report of the corrections."""
    print("=" * 80)
    print("CHEATING PROOF REJECTION REPORT")
    print("=" * 80)
    print(f"Experiment: {experiment_dir}")
    print()

    if dry_run:
        print("Mode: DRY RUN (no changes made)")
        print()

    if 'error' in stats:
        print(f"Error: {stats['error']}")
        return

    print("Summary:")
    print(f"  Total entries: {stats['total_entries']}")
    print(f"  Entries with cheating proofs: {stats['entries_corrected']}")
    print(f"  Proofs rejected: {stats['proofs_rejected']}")

    # Show breakdown by cheat type
    if stats.get('sorry_ax_count', 0) > 0 or stats.get('sorry_count', 0) > 0:
        print(f"    [sorryAx]: {stats.get('sorry_ax_count', 0)}")
        print(f"    [sorry]:   {stats.get('sorry_count', 0)}")

    print(f"  Sorries no longer verified: {stats['verified_lost']}")

    if stats.get('individual_files_updated', 0) > 0:
        print(f"  Individual files updated: {stats['individual_files_updated']}")

    if verbose and stats['rejected_details']:
        print()
        print("Details:")
        print("  Legend: [AX] = sorryAx, [S] = sorry")
        print()
        for detail in stats['rejected_details']:
            print(f"  - {detail['sorry_id']}")
            for rp in detail['rejected_proofs']:
                # Truncate long proofs
                proof_display = rp['proof'].strip().replace('\n', ' ')[:50]
                # Visual marker for cheat type
                if rp['cheat_type'] == 'sorryAx':
                    marker = "[AX]"
                else:
                    marker = "[S] "
                print(f"    {marker} \"{proof_display}\"")
            status = "still verified" if detail['still_verified'] else "no longer verified"
            print(f"    Status: {status}")

    if stats.get('backup_dir'):
        print()
        print(f"Backup created: {Path(stats['backup_dir']).name}/")

    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description='Reject cheating proofs (e.g., sorryAx, sorry) from experiment results'
    )
    parser.add_argument(
        'experiment_dir',
        help='Path to experiment directory containing result.json'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without modifying files'
    )
    parser.add_argument(
        '--run-analysis',
        action='store_true',
        help='Automatically regenerate analysis.json after correction'
    )
    parser.add_argument(
        '--just-sorry-ax',
        action='store_true',
        help='Only reject sorryAx proofs (not the sorry keyword)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed information about rejected proofs'
    )

    args = parser.parse_args()

    experiment_dir = Path(args.experiment_dir)
    if not experiment_dir.exists():
        print(f"Error: Directory not found: {experiment_dir}")
        sys.exit(1)

    # Get patterns based on flags
    patterns = get_cheating_patterns(just_sorry_ax=args.just_sorry_ax)

    # Process experiment
    stats = process_experiment(
        experiment_dir,
        patterns=patterns,
        dry_run=args.dry_run,
        run_analysis=args.run_analysis
    )

    # Print report
    print_report(stats, args.verbose, args.dry_run, experiment_dir)

    if stats.get('entries_corrected', 0) == 0:
        print("\nNo cheating proofs found. No changes needed.")


if __name__ == '__main__':
    main()
