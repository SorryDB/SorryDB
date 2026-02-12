#!/usr/bin/env python3
"""Generate a markdown case study of high-variance proofs."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import statistics

def discover_experiment_for_strategy(base_dir: Path, strategy: str, subfolder: str) -> Path:
    """Discover the experiment directory for a given strategy."""
    strategy_path = base_dir / strategy / subfolder

    if not strategy_path.exists():
        print(f"Error: Strategy path does not exist: {strategy_path}")
        sys.exit(1)

    experiment_dirs = [
        d for d in strategy_path.iterdir()
        if d.is_dir() and (d / "result.json").exists()
    ]

    if len(experiment_dirs) == 0:
        print(f"Error: No experiments found in {strategy_path}")
        sys.exit(1)

    if len(experiment_dirs) > 1:
        experiment_dirs = sorted(experiment_dirs, key=lambda d: d.name)
        return experiment_dirs[-1]

    return experiment_dirs[0]


def load_result_json(experiment_dir: Path) -> dict:
    """Load result.json and index by sorry_id."""
    result_path = experiment_dir / "result.json"
    with open(result_path) as f:
        data = json.load(f)

    # Index by sorry_id
    indexed = {}
    for entry in data:
        sorry_id = entry.get('sorry', {}).get('id')
        if sorry_id:
            indexed[sorry_id] = entry
    return indexed


def get_proof_for_sorry(result_data: dict, sorry_id: str) -> tuple:
    """Get proof and metadata for a sorry."""
    entry = result_data.get(sorry_id)
    if not entry:
        return None, None, None

    # Get successful attempts
    successful = entry.get('successful_attempts') or []
    if successful:
        # Return first successful proof
        proof = successful[0]
    else:
        proof = None

    # Get goal
    goal = entry.get('sorry', {}).get('debug_info', {}).get('goal', 'N/A')
    url = entry.get('sorry', {}).get('debug_info', {}).get('url', '')

    return proof, goal, url


def main():
    strategies = ['gemini', 'gemini_agentic', 'agentic', 'claude', 'goedel']
    base_dir = Path('intermediate_experiment_outputs_full_reservoir_3_months')
    subfolder = '1000'

    # Top 10 high variance sorry IDs (from previous analysis)
    high_variance_sorries = [
        '01270d4e589ee4ada3e33c7e0f348925fa3acbeb6f0f712fef800e42387cd307',
        'b96f409bddc5d1960db791e09e59e2b33a8df3e2066899e766672b26dad2683f',
        '0d142d71c38d8080d020b76b7807b130d7c8134c3bbfee785321599905013f86',
        'a4a97c3e76902005a0423851593f4572c11a53fa63b5ff3a72f04beebb0ffaa3',
        '87d1bb7b559539e7d2ea834032d5326d01adbf1e4a2f88247590f01c2437c8ab',
        '7c97d7ee16e6979a2e7c5e2ea8f3d8b9c217cfb4347cfa3e2f38a3a389fb5f4a',
        '3fd2b4440ee748a8296ce8688dba26e59a70abb13d51e018d5917ecae66c3683',
        'd7d1fbf0291732f61dc0989d052052578efe7bdaf36c6b9ce6a06c3120ce0583',
        'cb840a6a3487ae484fc54acaf23ee2911c248a266fcb419d34908147f85db668',
        'e2f7fb98eac7f85032edae40e10c6cc36e8c407209720c786e1903510729efc1',
    ]

    # Load result data for each strategy
    print("Loading result data...")
    result_data = {}
    for strategy in strategies:
        exp_dir = discover_experiment_for_strategy(base_dir, strategy, subfolder)
        print(f"  {strategy}: {exp_dir.name}")
        result_data[strategy] = load_result_json(exp_dir)

    # Generate markdown
    md_lines = [
        "# Proof Length Case Study: High Variance Examples",
        "",
        "This document analyzes sorries where different strategies produced proofs with significantly different lengths.",
        "These examples highlight how different approaches can lead to vastly different proof styles.",
        "",
        "**Strategies compared:**",
        "- `gemini`: Gemini Flash (pass@32)",
        "- `gemini_agentic`: Gemini Flash with self-correction",
        "- `agentic`: Claude Opus with self-correction",
        "- `claude`: Claude Opus (pass@32)",
        "- `goedel`: Goedel Prover V2",
        "",
        "---",
        "",
    ]

    for i, sorry_id in enumerate(high_variance_sorries, 1):
        # Get proof and metadata from first available strategy
        proof, goal, url = None, None, None
        for strategy in strategies:
            p, g, u = get_proof_for_sorry(result_data[strategy], sorry_id)
            if g and g != 'N/A':
                goal = g
                url = u
                break

        md_lines.append(f"## Case {i}: `{sorry_id[:16]}...`")
        md_lines.append("")

        if url:
            md_lines.append(f"**Source:** [{url}]({url})")
            md_lines.append("")

        md_lines.append("### Goal")
        md_lines.append("```lean")
        md_lines.append(goal or "N/A")
        md_lines.append("```")
        md_lines.append("")

        md_lines.append("### Proof Lengths")
        md_lines.append("")
        md_lines.append("| Strategy | Length (chars) |")
        md_lines.append("|----------|----------------|")

        lengths = {}
        for strategy in strategies:
            proof, _, _ = get_proof_for_sorry(result_data[strategy], sorry_id)
            if proof:
                length = len(proof)
                lengths[strategy] = length
                md_lines.append(f"| {strategy} | {length} |")
            else:
                md_lines.append(f"| {strategy} | N/A |")

        md_lines.append("")

        # Calculate stats
        if lengths:
            values = list(lengths.values())
            md_lines.append(f"**Range:** {max(values) - min(values)} chars | **Std Dev:** {statistics.stdev(values):.1f}")
            md_lines.append("")

        md_lines.append("### Proofs")
        md_lines.append("")

        for strategy in strategies:
            proof, _, _ = get_proof_for_sorry(result_data[strategy], sorry_id)
            md_lines.append(f"#### {strategy}")
            md_lines.append("```lean")
            if proof:
                md_lines.append(proof.strip())
            else:
                md_lines.append("-- No proof available")
            md_lines.append("```")
            md_lines.append("")

        # Add analysis placeholder
        md_lines.append("### Analysis")
        md_lines.append("")

        if lengths:
            shortest = min(lengths, key=lengths.get)
            longest = max(lengths, key=lengths.get)
            md_lines.append(f"**Shortest:** {shortest} ({lengths[shortest]} chars)")
            md_lines.append(f"**Longest:** {longest} ({lengths[longest]} chars)")
            md_lines.append(f"**Ratio:** {lengths[longest] / lengths[shortest]:.1f}x")
            md_lines.append("")

        md_lines.append("---")
        md_lines.append("")

    # Write markdown file
    output_path = Path("proof_length_case_study.md")
    with open(output_path, 'w') as f:
        f.write('\n'.join(md_lines))

    print(f"\nGenerated: {output_path}")


if __name__ == '__main__':
    main()
