# ELO Ratings for SorryDB

Bradley-Terry strength ratings for models on the SorryDB benchmark, computed via [RatingExperiments](../RatingExperiments).

## Quick Start

### 1. Generate attempts JSON

Aggregates experiment `result.json` files (with rerun merging) into the flat format expected by `rate.py`:

```bash
python3 scripts/generate_rating_attempts.py \
    --base-dir intermediate_experiment_outputs_full_reservoir_3_months \
    --strategies claude gemini gemini-pro gpt agentic gemini_agentic gemini_agentic_tools goedel multi_tactic qwen rfl \
    --subfolder 1000 \
    --output rating_attempts.json
```

Output: `rating_attempts.json` — a JSON array of `{"agent", "problem", "outcome"}` objects.

### 2. Compute ratings

```bash
python ../RatingExperiments/rate.py rating_attempts.json --output_file ratings.json
```

Requires `jax` and `numpy` (`uv pip install jax jaxlib`). First run is slow (~5-10 min) due to JAX JIT compilation.

Output: `ratings.json` with agent strengths, problem difficulties, and standard errors.

### 3. Plot ELO vs Solve Fraction

```bash
python3 -c "
import json, matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

with open('ratings.json') as f:
    data = json.load(f)

agents = data['agents']
elos = [a['strength'] * 173.7 + 1500 for a in agents]
fracs = [a['solved_per_attempt'] for a in agents]
errs = [a['std_error'] * 173.7 for a in agents]

fig, ax = plt.subplots(figsize=(10, 6))
ax.errorbar(fracs, elos, yerr=errs, fmt='o', markersize=8, capsize=4, color='steelblue')
for a, f, e in zip(agents, fracs, elos):
    ax.annotate(a['id'], (f, e), textcoords='offset points', xytext=(8, 5), fontsize=8)
ax.set_xlabel('Solve Fraction'); ax.set_ylabel('ELO Rating')
ax.set_title('ELO Rating vs Solve Fraction'); ax.grid(True, alpha=0.3)
plt.tight_layout(); plt.savefig('charts/elo_vs_solved.png', dpi=200, bbox_inches='tight')
print('Saved to charts/elo_vs_solved.png')
"
```

## ELO Conversion

Raw Bradley-Terry strengths are centered at 0. To convert to the chess ELO scale:

```
ELO = strength * 173.7 + 1500
```

## Available Strategies

| Directory | Agent Name | Notes |
|---|---|---|
| `claude` | claude-opus-4-5 | Pass@32 LLM |
| `gemini` | gemini-3-flash-preview | Pass@32 LLM |
| `gemini-pro` | gemini-3-pro-preview | Pass@32 LLM |
| `gpt` | gpt-5.2 | Pass@32 LLM |
| `goedel` | goedel | Pass@32 specialized LLM |
| `qwen` | qwen | Pass@32 LLM |
| `agentic` | claude-opus-4-5 (agentic) | Iterative (SC) |
| `gemini_agentic` | gemini-3-flash-preview (agentic) | Iterative (SC) |
| `gemini_agentic_tools` | gemini-3-flash-preview (agentic w/ tools) | Iterative with tools |
| `multi_tactic` | multi_tactic | Deterministic tactics |
| `rfl` | rfl | Single tactic |

Not all strategies have a `1000` subfolder (e.g., `kimina`, `aristotle` are missing it).
