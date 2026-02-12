#!/usr/bin/env python3
"""Find sorries with highest variance in proof length across strategies."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import statistics

# Extract proof lengths
strategies = ['gemini', 'gemini_agentic', 'agentic', 'claude', 'goedel']
base_dir = 'intermediate_experiment_outputs_full_reservoir_3_months'
subfolder = '1000'

with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
    temp_output = f.name

cmd = [
    sys.executable,
    'scripts/extract_proof_lengths.py',
    '--base-dir', base_dir,
    '--strategies', *strategies,
    '--subfolder', subfolder,
    '--output', temp_output
]

result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    print(result.stderr)
    sys.exit(1)

with open(temp_output) as f:
    data = json.load(f)

Path(temp_output).unlink()

by_sorry = data['by_sorry_strategy']

# Find sorries solved by ALL strategies
common_sorries = []
for sorry_id, strat_data in by_sorry.items():
    if all(s in strat_data for s in strategies):
        common_sorries.append(sorry_id)

print(f'Sorries solved by all {len(strategies)} strategies: {len(common_sorries)}')
print()

# Calculate variance for each sorry
sorry_variances = []
for sorry_id in common_sorries:
    lengths = [by_sorry[sorry_id][s]['avg_length'] for s in strategies]
    variance = statistics.variance(lengths)
    stdev = statistics.stdev(lengths)
    sorry_variances.append({
        'sorry_id': sorry_id,
        'variance': variance,
        'stdev': stdev,
        'lengths': {s: by_sorry[sorry_id][s]['avg_length'] for s in strategies},
        'min': min(lengths),
        'max': max(lengths),
        'range': max(lengths) - min(lengths)
    })

# Sort by variance (descending)
sorry_variances.sort(key=lambda x: x['variance'], reverse=True)

# Print top 10
print('Top 10 sorries with highest variance in proof length:')
print('=' * 100)
for i, sv in enumerate(sorry_variances[:10], 1):
    print(f'{i}. Sorry ID: {sv["sorry_id"]}')
    print(f'   Variance: {sv["variance"]:.1f}, Std Dev: {sv["stdev"]:.1f}, Range: {sv["range"]:.1f}')
    print(f'   Lengths by strategy:')
    for s in strategies:
        print(f'      {s:20s}: {sv["lengths"][s]:8.1f} chars')
    print()
