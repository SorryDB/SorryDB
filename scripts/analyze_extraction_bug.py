#!/usr/bin/env python3
"""
Analyze experiment logs to find cases affected by the extract_proof_from_diff bug.

The bug: When extracting proofs, short spurious matches (like " s" from " sorry"
matching " s" from " simp") can overwrite correct long matches, causing only
partial proofs to be extracted.

Usage:
    python scripts/analyze_extraction_bug.py <experiment_dir> [--output full_llm_responses.json]

Example:
    python scripts/analyze_extraction_bug.py intermediate_experiment_outputs_full_reservoir_3_months/goedel/1000/2026-01-18_18-00-23_llm
"""

import argparse
import json
import re
from pathlib import Path
from collections import defaultdict


def extract_responses_from_log(log_path: Path) -> list[dict]:
    """Extract all LLM response/extraction pairs from a single log file."""
    content = log_path.read_text()

    # Pattern to match log lines: [YYYY-MM-DD HH:MM:SS]
    log_line_pattern = r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]'

    responses = []

    # Find all "Full LLM response:" occurrences
    response_starts = list(re.finditer(r'\[INFO\] Full LLM response:\n', content))

    for i, match in enumerate(response_starts):
        start_pos = match.end()

        # Find where this response ends (next log line)
        next_log = re.search(log_line_pattern, content[start_pos:])
        if next_log:
            end_pos = start_pos + next_log.start()
        else:
            end_pos = len(content)

        llm_response = content[start_pos:end_pos].rstrip()

        # Find "Extracted proof:" and capture until next log line (supports multi-line proofs)
        extracted_proof = None
        extraction_search_start = end_pos
        extraction_marker = '[INFO] Extracted proof:'
        marker_pos = content.find(extraction_marker, extraction_search_start)

        if marker_pos != -1 and marker_pos < extraction_search_start + 1000:
            proof_start = marker_pos + len(extraction_marker)
            # Find next log timestamp after proof
            next_log_after_proof = re.search(log_line_pattern, content[proof_start:])
            if next_log_after_proof:
                proof_end = proof_start + next_log_after_proof.start()
            else:
                proof_end = len(content)
            extracted_proof = content[proof_start:proof_end].strip()

        responses.append({
            'llm_response': llm_response,
            'extracted_proof': extracted_proof,
            'log_file': log_path.name,
        })

    return responses


def check_for_bug(llm_response: str, extracted_proof: str | None) -> dict:
    """
    Check if a response/extraction pair shows signs of the bug.

    Signs of the bug:
    1. LLM response contains a tactic starting with 's' (simp, simp_all, subst, etc.)
    2. Extracted proof is much shorter than expected
    3. Extracted proof starts with a tactic that appears late in the LLM response
    """
    if not extracted_proof or not llm_response:
        return {'potentially_affected': False, 'reason': 'empty_response_or_proof'}

    # Strip markdown from LLM response to get actual code
    code = llm_response
    if '```lean' in code:
        parts = code.split('```lean')
        for part in parts[1:]:
            if '```' in part:
                code = part.split('```')[0]
                break

    # Check for s-starting tactics in the code
    s_tactics = ['simp', 'simp_all', 'subst', 'split', 'specialize', 'sorry',
                 'set', 'show', 'suffices', 'symm', 'swap', 'skip']

    found_s_tactics = []
    for tactic in s_tactics:
        # Look for " {tactic}" pattern (space before tactic)
        if f' {tactic}' in code:
            found_s_tactics.append(tactic)

    # Check if extracted proof looks like it starts mid-proof
    suspicious_starts = ['imp', 'imp_all', 'ubst', 'plit', 'et', 'how']  # Partial tactic names
    starts_suspicious = any(extracted_proof.strip().startswith(s) for s in suspicious_starts)

    # Check if extracted proof is very short compared to code
    code_lines = len([l for l in code.split('\n') if l.strip()])
    proof_lines = len([l for l in extracted_proof.split('\n') if l.strip()])

    # Heuristic: if code has many lines but proof has few, might be truncated
    possibly_truncated = code_lines > 5 and proof_lines <= 2

    # Check if extracted proof appears late in the LLM response
    proof_stripped = extracted_proof.strip()
    if proof_stripped and proof_stripped in code:
        proof_pos = code.find(proof_stripped)
        code_len = len(code)
        # If proof appears in latter half of code, might be bug
        appears_late = proof_pos > code_len * 0.5
    else:
        appears_late = False

    potentially_affected = (
        len(found_s_tactics) > 0 and
        (starts_suspicious or possibly_truncated or appears_late)
    )

    return {
        'potentially_affected': potentially_affected,
        's_tactics_found': found_s_tactics,
        'starts_suspicious': starts_suspicious,
        'possibly_truncated': possibly_truncated,
        'appears_late': appears_late,
        'code_lines': code_lines,
        'proof_lines': proof_lines,
    }


def analyze_experiment(experiment_dir: Path, output_path: Path | None = None):
    """Analyze all log files in an experiment directory."""
    # Check both possible log locations
    logs_dir = experiment_dir / 'logs' / 'process_single_sorry'
    remote_logs_dir = experiment_dir / 'logs' / 'remote_morph_logs'

    log_files = []
    if logs_dir.exists():
        log_files.extend(logs_dir.glob('*.log'))
    if remote_logs_dir.exists():
        log_files.extend(remote_logs_dir.glob('*.log'))

    if not log_files:
        print(f"Error: No log files found in {logs_dir} or {remote_logs_dir}")
        return
    print(f"Found {len(log_files)} log files")

    all_responses = []
    stats = defaultdict(int)

    for log_file in log_files:
        responses = extract_responses_from_log(log_file)

        for resp in responses:
            bug_check = check_for_bug(resp['llm_response'], resp['extracted_proof'])
            resp['bug_analysis'] = bug_check

            if bug_check['potentially_affected']:
                stats['potentially_affected'] += 1
            stats['total_responses'] += 1

        all_responses.extend(responses)

    # Summary
    print("\n=== Analysis Summary ===")
    print(f"Total responses analyzed: {stats['total_responses']}")
    print(f"Potentially affected by bug: {stats['potentially_affected']}")
    print(f"Percentage: {stats['potentially_affected'] / max(stats['total_responses'], 1) * 100:.1f}%")

    # Save to JSON
    if output_path is None:
        output_path = experiment_dir / 'full_llm_responses.json'

    output_data = {
        'experiment_dir': str(experiment_dir),
        'stats': dict(stats),
        'responses': all_responses,
    }

    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\nSaved {len(all_responses)} responses to {output_path}")

    # Show some examples of potentially affected cases
    affected = [r for r in all_responses if r['bug_analysis']['potentially_affected']]
    if affected:
        print("\n=== Examples of potentially affected cases ===")
        for resp in affected[:3]:
            print(f"\nLog file: {resp['log_file']}")
            print(f"S-tactics found: {resp['bug_analysis']['s_tactics_found']}")
            print(f"Extracted proof: {repr(resp['extracted_proof'][:100])}...")
            print(f"Code lines: {resp['bug_analysis']['code_lines']}, Proof lines: {resp['bug_analysis']['proof_lines']}")


def verify_bug_with_difflib(llm_response: str, extracted_proof: str | None) -> dict | None:
    """
    Actually verify if the bug manifests by checking difflib matching blocks.

    Returns details if bug is confirmed, None otherwise.
    """
    import difflib

    if not extracted_proof or not llm_response:
        return None

    # Strip markdown from LLM response
    code = llm_response
    if '```lean' in code:
        parts = code.split('```lean')
        complete_blocks = []
        for part in parts[1:]:
            if '```' in part:
                block_content = part.split('```')[0]
                complete_blocks.append(block_content)
        if complete_blocks:
            code = complete_blocks[-1]
    code = code.strip('`').strip()

    # For simplicity, create a synthetic "original" that ends with "by sorry"
    # This simulates the common case
    if 'by' not in code:
        return None

    # Find last "by" in the code and create synthetic original
    by_pos = code.rfind(':= by')
    if by_pos == -1:
        by_pos = code.rfind(' by\n')
    if by_pos == -1:
        return None

    # Synthetic original: everything up to "by" + " sorry"
    synthetic_original = code[:by_pos + 5] + ' sorry'  # ":= by" is 5 chars

    # Check difflib blocks
    matcher = difflib.SequenceMatcher(None, synthetic_original, code, autojunk=False)
    blocks = matcher.get_matching_blocks()

    # Find blocks before "sorry" position
    sorry_start = len(synthetic_original) - 5  # Position of 's' in sorry

    blocks_before_sorry = []
    for i, j, n in blocks:
        if n > 0 and i < sorry_start:
            blocks_before_sorry.append((i, j, n))

    if len(blocks_before_sorry) < 2:
        return None

    # Check if there's a long block followed by a short block
    # Sort by position in original
    blocks_before_sorry.sort(key=lambda b: b[0])

    # Find the longest block
    longest = max(blocks_before_sorry, key=lambda b: b[2])
    # Find the last block (highest position)
    last = max(blocks_before_sorry, key=lambda b: b[0])

    # Bug manifests if: last block is shorter than longest AND last block is different from longest
    if last != longest and last[2] < longest[2]:
        # The short match would overwrite the long match
        return {
            'confirmed': True,
            'longest_block': {'orig_pos': longest[0], 'llm_pos': longest[1], 'length': longest[2]},
            'last_block': {'orig_pos': last[0], 'llm_pos': last[1], 'length': last[2]},
            'synthetic_original_len': len(synthetic_original),
            'code_len': len(code),
        }

    return None


def detailed_bug_analysis(experiment_dir: Path):
    """Run detailed bug verification on responses."""
    json_path = experiment_dir / 'full_llm_responses.json'

    if not json_path.exists():
        print(f"Error: Run basic analysis first to generate {json_path}")
        return

    with open(json_path) as f:
        data = json.load(f)

    confirmed_bugs = []
    for resp in data['responses']:
        result = verify_bug_with_difflib(resp['llm_response'], resp['extracted_proof'])
        if result and result.get('confirmed'):
            confirmed_bugs.append({
                'log_file': resp['log_file'],
                'extracted_proof': resp['extracted_proof'][:100] if resp['extracted_proof'] else None,
                'bug_details': result,
            })

    print("\n=== Detailed Bug Verification ===")
    print(f"Total responses: {len(data['responses'])}")
    print(f"Confirmed bug cases: {len(confirmed_bugs)}")
    print(f"Percentage: {len(confirmed_bugs) / max(len(data['responses']), 1) * 100:.1f}%")

    if confirmed_bugs:
        print("\n=== Confirmed bug examples ===")
        for bug in confirmed_bugs[:5]:
            print(f"\nLog: {bug['log_file']}")
            print(f"Longest block: {bug['bug_details']['longest_block']}")
            print(f"Last block (overwrites): {bug['bug_details']['last_block']}")
            print(f"Extracted: {repr(bug['extracted_proof'])}...")

    return confirmed_bugs


def main():
    parser = argparse.ArgumentParser(description='Analyze extraction bug in experiment logs')
    parser.add_argument('experiment_dir', type=Path, help='Path to experiment directory')
    parser.add_argument('--output', '-o', type=Path, help='Output JSON path')
    parser.add_argument('--verify', action='store_true', help='Run detailed bug verification')

    args = parser.parse_args()

    if args.verify:
        detailed_bug_analysis(args.experiment_dir)
    else:
        analyze_experiment(args.experiment_dir, args.output)


if __name__ == '__main__':
    main()
