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

### 3. Plot charts

```bash
python3 charts/plot_elo_vs_solved.py
python3 charts/plot_problem_difficulty.py
```

## Results

| Name | Accuracy | ELO |
|---|---|---|
| Gemini Flash 3 (Agentic) | 30.3% | 1859 |
| Gemini Flash 3 (SC) | 27.9% | 1775 |
| Claude Opus 4.5 (SC) | 27.1% | 1751 |
| Gemini Pro 3 | 20.6% | 1582 |
| Gemini Flash 3 | 20.5% | 1579 |
| Claude Opus 4.5 | 15.4% | 1457 |
| GPT 5.2 | 13.2% | 1403 |
| Goedel Prover V2 32B | 11.3% | 1354 |
| Tactics | 8.4% | 1270 |
| Qwen 3 | 8.1% | 1260 |
| Kimina Prover 8B | 6.6% | 1210 |

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
