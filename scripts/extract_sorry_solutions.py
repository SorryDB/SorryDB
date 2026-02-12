#!/usr/bin/env python3
"""
Extract all proposed solutions for a specific sorry across multiple strategies.

Discovers experiments by strategy name and subfolder, then extracts all proof
attempts (both successful and failed) for a specific sorry ID.

Usage:
    python scripts/extract_sorry_solutions.py \
        --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
        --strategies agentic gemini multi_tactic claude goedel gemini_agentic \
        --subfolder 1000 \
        --sorry-id <sorry_id> \
        --output solutions.md
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class SorryInfo:
    """Information about a sorry from the result."""
    id: str
    repo_url: str
    file_path: str
    line: int
    goal: str
    github_url: Optional[str] = None  # Direct GitHub URL if available


@dataclass
class StrategyResult:
    """Results from a single strategy for a sorry."""
    strategy_name: str
    proof_verified: bool
    successful_proof: Optional[str]
    failed_attempts: List[str]
    verification_message: Optional[str]
    feedback: Optional[str]
    error_type: Optional[str]
    error_message: Optional[str]


def discover_experiment_for_strategy(base_dir: Path, strategy: str, subfolder: str) -> Path:
    """
    Discover the experiment directory for a given strategy and subfolder.

    Args:
        base_dir: Base directory containing strategy folders
        strategy: Strategy name (e.g., 'claude', 'gemini')
        subfolder: Subfolder within strategy (e.g., '1000')

    Returns:
        Path to the experiment directory

    Raises:
        SystemExit: If zero or multiple experiments found
    """
    strategy_path = base_dir / strategy / subfolder

    if not strategy_path.exists():
        print(f"Error: Strategy path does not exist: {strategy_path}", file=sys.stderr)
        sys.exit(1)

    # Find all subdirectories containing result.json
    experiment_dirs = [
        d for d in strategy_path.iterdir()
        if d.is_dir() and (d / "result.json").exists()
    ]

    if len(experiment_dirs) == 0:
        print(f"Error: No experiments found in {strategy_path}", file=sys.stderr)
        print("(Looking for subdirectories containing result.json)", file=sys.stderr)
        sys.exit(1)

    if len(experiment_dirs) > 1:
        # Sort by directory name (timestamp format YYYY-MM-DD_HH-MM-SS_*) and pick most recent
        experiment_dirs = sorted(experiment_dirs, key=lambda d: d.name)
        print(f"  Note: Multiple experiments found, using most recent: {experiment_dirs[-1].name}",
              file=sys.stderr)
        return experiment_dirs[-1]

    return experiment_dirs[0]


def find_sorry_in_results(result_json_path: Path, sorry_id: str) -> Optional[Dict[str, Any]]:
    """
    Find a specific sorry entry in a result.json file.

    Args:
        result_json_path: Path to result.json file
        sorry_id: The sorry ID to search for

    Returns:
        The matching entry dict, or None if not found
    """
    with open(result_json_path, 'r') as f:
        data = json.load(f)

    for entry in data:
        entry_sorry_id = entry.get('sorry', {}).get('id')
        if entry_sorry_id == sorry_id:
            return entry

    return None


def extract_sorry_info(entry: Dict[str, Any]) -> SorryInfo:
    """Extract sorry metadata from a result entry."""
    sorry = entry.get('sorry', {})
    location = sorry.get('location', {})
    debug_info = sorry.get('debug_info', {})
    repo = sorry.get('repo', {})

    return SorryInfo(
        id=sorry.get('id', ''),
        repo_url=repo.get('remote', ''),
        file_path=location.get('path', ''),
        line=location.get('start_line', 0),
        goal=debug_info.get('goal', ''),
        github_url=debug_info.get('url'),
    )


def extract_strategy_result(entry: Dict[str, Any], strategy_name: str) -> StrategyResult:
    """Extract the proof attempts from a result entry."""
    return StrategyResult(
        strategy_name=strategy_name,
        proof_verified=entry.get('proof_verified', False),
        successful_proof=entry.get('proof') if entry.get('proof') else None,
        failed_attempts=entry.get('failed_attempts') or [],
        verification_message=entry.get('verification_message'),
        feedback=entry.get('feedback'),
        error_type=entry.get('error_type'),
        error_message=entry.get('error_message'),
    )


def try_load_individual_iterations(
    experiment_dir: Path,
    sorry_id: str
) -> Optional[List[Dict[str, Any]]]:
    """
    Try to load individual iteration results for agentic strategies.

    Args:
        experiment_dir: Path to experiment directory
        sorry_id: The sorry ID

    Returns:
        List of iteration results, or None if not available
    """
    individual_file = experiment_dir / "individual" / f"{sorry_id}.json"
    if individual_file.exists():
        with open(individual_file, 'r') as f:
            return json.load(f)
    return None


def format_proof_block(proof: str, index: Optional[int] = None, verified: Optional[bool] = None) -> str:
    """Format a proof as a markdown code block with optional metadata."""
    lines = []
    if index is not None:
        status = ""
        if verified is not None:
            status = " ✓" if verified else " ✗"
        lines.append(f"**Attempt {index}{status}:**")
    lines.append("```lean4")
    lines.append(proof.strip() if proof else "(empty)")
    lines.append("```")
    return "\n".join(lines)


def generate_markdown(
    sorry_info: SorryInfo,
    results: List[StrategyResult],
    individual_iterations: Dict[str, List[Dict[str, Any]]]
) -> str:
    """Generate markdown report for all strategy results."""
    lines = []

    # Header
    lines.append("# Sorry Solutions Report")
    lines.append("")

    # Sorry metadata
    lines.append("## Sorry Information")
    lines.append("")
    lines.append(f"**ID:** `{sorry_info.id}`")
    lines.append("")

    # Generate GitHub link
    if sorry_info.github_url:
        # Use the direct GitHub URL from debug_info
        repo_url = sorry_info.repo_url.rstrip('/').removesuffix('.git')
        repo_name = repo_url.replace('https://github.com/', '') if repo_url.startswith('https://github.com/') else repo_url
        lines.append(f"**Location:** [{repo_name}]({sorry_info.github_url}) - {sorry_info.file_path}:{sorry_info.line}")
    else:
        repo_url = sorry_info.repo_url.rstrip('/').removesuffix('.git')
        if repo_url.startswith('https://github.com/'):
            repo_name = repo_url.replace('https://github.com/', '')
            github_link = f"{repo_url}/blob/HEAD/{sorry_info.file_path}#L{sorry_info.line}"
            lines.append(f"**Location:** [{repo_name}]({github_link}) - {sorry_info.file_path}:{sorry_info.line}")
        else:
            lines.append(f"**Repository:** {sorry_info.repo_url}")
            lines.append(f"**File:** {sorry_info.file_path}:{sorry_info.line}")
    lines.append("")

    # Goal
    lines.append("**Goal:**")
    lines.append("```lean")
    lines.append(sorry_info.goal.strip() if sorry_info.goal else "(not available)")
    lines.append("```")
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Strategy | Verified | Total Attempts |")
    lines.append("|----------|----------|----------------|")
    for result in results:
        total = len(result.failed_attempts) + (1 if result.successful_proof else 0)
        status = "✓" if result.proof_verified else "✗"
        lines.append(f"| {result.strategy_name} | {status} | {total} |")
    lines.append("")

    # Results per strategy
    lines.append("## Solutions by Strategy")
    lines.append("")

    for result in results:
        lines.append(f"### {result.strategy_name}")
        lines.append("")

        if result.proof_verified and result.successful_proof:
            lines.append("**Status:** ✓ Verified")
            lines.append("")
            lines.append("**Successful Proof:**")
            lines.append("```lean4")
            lines.append(result.successful_proof.strip())
            lines.append("```")
        elif result.successful_proof:
            lines.append("**Status:** Proof found but not verified")
            lines.append("")
            lines.append("**Proof:**")
            lines.append("```lean4")
            lines.append(result.successful_proof.strip())
            lines.append("```")
        else:
            lines.append("**Status:** ✗ No successful proof")
        lines.append("")

        # Show additional info if available
        if result.verification_message:
            lines.append(f"**Verification:** {result.verification_message}")
            lines.append("")

        if result.error_type:
            lines.append(f"**Error Type:** {result.error_type}")
            if result.error_message:
                lines.append(f"**Error:** {result.error_message[:500]}")
            lines.append("")

        # Check for individual iterations (agentic strategies)
        if result.strategy_name in individual_iterations:
            iterations = individual_iterations[result.strategy_name]
            if len(iterations) > 1:
                lines.append(f"#### Iterations ({len(iterations)} total)")
                lines.append("")
                for i, iteration in enumerate(iterations, 1):
                    verified = iteration.get('proof_verified', False)
                    proof = iteration.get('proof', '')
                    status = "✓" if verified else "✗"
                    lines.append(f"**Iteration {i} {status}:**")
                    if proof:
                        lines.append("```lean4")
                        lines.append(proof.strip())
                        lines.append("```")
                    else:
                        lines.append("*(no proof)*")

                    # Show feedback if available
                    feedback = iteration.get('feedback')
                    if feedback and not verified:
                        lines.append(f"*Feedback:* {feedback[:300]}...")
                    lines.append("")

        # Show failed attempts
        if result.failed_attempts:
            lines.append(f"#### Failed Attempts ({len(result.failed_attempts)})")
            lines.append("")

            # Deduplicate and count
            attempt_counts: Dict[str, int] = {}
            for attempt in result.failed_attempts:
                attempt_counts[attempt] = attempt_counts.get(attempt, 0) + 1

            # Show unique attempts with counts
            for i, (attempt, count) in enumerate(attempt_counts.items(), 1):
                count_str = f" (×{count})" if count > 1 else ""
                lines.append(f"**Attempt {i}{count_str}:**")
                lines.append("```lean4")
                lines.append(attempt.strip() if attempt.strip() else "(empty)")
                lines.append("```")
                lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Extract all proposed solutions for a specific sorry across strategies'
    )
    parser.add_argument(
        '--base-dir',
        required=True,
        help='Base directory containing strategy folders'
    )
    parser.add_argument(
        '--strategies',
        nargs='+',
        required=True,
        help='List of strategy names to include'
    )
    parser.add_argument(
        '--subfolder',
        required=True,
        help='Subfolder within each strategy (e.g., "1000")'
    )
    parser.add_argument(
        '--sorry-id',
        required=True,
        help='The sorry ID to extract solutions for'
    )
    parser.add_argument(
        '--output', '-o',
        default='sorry_solutions.md',
        help='Output markdown file (default: sorry_solutions.md)'
    )

    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        print(f"Error: Base directory does not exist: {base_dir}", file=sys.stderr)
        sys.exit(1)

    # Discover experiment directories and collect results
    print(f"Searching for sorry {args.sorry_id}...", file=sys.stderr)
    print(f"Base directory: {base_dir}", file=sys.stderr)
    print(file=sys.stderr)

    results: List[StrategyResult] = []
    individual_iterations: Dict[str, List[Dict[str, Any]]] = {}
    sorry_info: Optional[SorryInfo] = None

    for strategy in args.strategies:
        print(f"  Checking {strategy}...", file=sys.stderr)
        try:
            experiment_dir = discover_experiment_for_strategy(base_dir, strategy, args.subfolder)
        except SystemExit:
            print(f"    Skipping {strategy} (no experiment found)", file=sys.stderr)
            continue

        result_json = experiment_dir / "result.json"
        entry = find_sorry_in_results(result_json, args.sorry_id)

        if entry is None:
            print(f"    Sorry not found in {strategy}", file=sys.stderr)
            continue

        print(f"    Found in {experiment_dir.name}", file=sys.stderr)

        # Extract sorry info (only need to do this once)
        if sorry_info is None:
            sorry_info = extract_sorry_info(entry)

        # Extract strategy result
        strategy_result = extract_strategy_result(entry, strategy)
        results.append(strategy_result)

        # Try to load individual iterations for agentic strategies
        if 'agentic' in strategy.lower():
            iterations = try_load_individual_iterations(experiment_dir, args.sorry_id)
            if iterations and len(iterations) > 1:
                individual_iterations[strategy] = iterations

    if sorry_info is None:
        print(f"\nError: Sorry ID {args.sorry_id} not found in any strategy", file=sys.stderr)
        sys.exit(1)

    if not results:
        print(f"\nError: No results found for sorry ID {args.sorry_id}", file=sys.stderr)
        sys.exit(1)

    print(f"\nFound {len(results)} strategies with results", file=sys.stderr)

    # Generate markdown
    markdown = generate_markdown(sorry_info, results, individual_iterations)

    # Write output
    output_path = Path(args.output)
    with open(output_path, 'w') as f:
        f.write(markdown)

    print(f"Written to {output_path}", file=sys.stderr)


if __name__ == '__main__':
    main()
