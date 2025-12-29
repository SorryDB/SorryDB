# Experiment Comparison: anthropic vs deepseek vs google vs rfl vs supersimple

## Summary Comparison

| Metric | anthropic | deepseek | google | rfl | supersimple |
|--------|---------|---------|---------|---------|---------|
| Total Repositories | 29 | 29 | 29 | 29 | 29 |
| Total Sorries | 96 | 96 | 96 | 96 | 96 |
| Total Verified | 9 | 10 | 10 | 1 | 9 |
| Total Failed | 87 | 86 | 86 | 95 | 87 |
| Overall Success Rate | 9.38% | 10.42% | 10.42% | 1.04% | 9.38% |

## Results by Repository

Sorted by variance (biggest differences across experiments)

| Repository | anthropic (V/T) | anthropic Rate | deepseek (V/T) | deepseek Rate | google (V/T) | google Rate | rfl (V/T) | rfl Rate | supersimple (V/T) | supersimple Rate |
|-----------|---------------|--------------|---------------|--------------|---------------|--------------|---------------|--------------|---------------|--------------|
| cmu-l3/llmlean | 3/3 | 100.0% | 2/3 | 66.7% | 3/3 | 100.0% | 0/3 | 0.0% | 2/3 | 66.7% |
| frenzymath/jixia | 1/2 | 50.0% | 2/2 | 100.0% | 1/2 | 50.0% | 0/2 | 0.0% | 0/2 | 0.0% |
| leanprover/verso | 2/3 | 66.7% | 2/3 | 66.7% | 2/3 | 66.7% | 0/3 | 0.0% | 0/3 | 0.0% |
| mo271/FormalBook | 1/3 | 33.3% | 1/3 | 33.3% | 1/3 | 33.3% | 0/3 | 0.0% | 2/3 | 66.7% |
| leanprover-community/NNG4 | 2/3 | 66.7% | 2/3 | 66.7% | 2/3 | 66.7% | 1/3 | 33.3% | 2/3 | 66.7% |
| yangky11/miniF2F-lean4 | 0/3 | 0.0% | 1/3 | 33.3% | 1/3 | 33.3% | 0/3 | 0.0% | 1/3 | 33.3% |
| FormalizedFormalLogic/Foundation | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 1/4 | 25.0% |
| PatrickMassot/GlimpseOfLean | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 1/4 | 25.0% |
| AlexKontorovich/PrimeNumberTheoremAnd | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% |
| HEPLean/PhysLean | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% |
| ImperialCollegeLondon/FLT | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% |
| Verified-zkEVM/ZKLib | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% |
| YaelDillies/LeanCamCombi | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% |
| alexkeizer/QpfTypes | 0/2 | 0.0% | 0/2 | 0.0% | 0/2 | 0.0% | 0/2 | 0.0% | 0/2 | 0.0% |
| dwrensha/compfiles | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% |
| emilyriehl/infinity-cosmos | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% |
| eric-wieser/lean-matrix-cookbook | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% |
| fpvandoorn/carleson | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% |
| leanprover-community/aesop | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% |
| leanprover-community/batteries | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% |
| leanprover-community/duper | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% |
| leanprover-community/iris-lean | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% |
| leanprover-community/mathlib4 | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% |
| leanprover-community/quote4 | 0/1 | 0.0% | 0/1 | 0.0% | 0/1 | 0.0% | 0/1 | 0.0% | 0/1 | 0.0% |
| leanprover-community/sphere-eversion | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% |
| lecopivo/SciLean | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% |
| nomeata/loogle | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% |
| teorth/pfr | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% | 0/4 | 0.0% |
| ufmg-smite/lean-smt | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% | 0/3 | 0.0% |

## Legend

- **V/T**: Verified / Total sorries
- **Rate**: Success rate percentage
- **—**: No data for this experiment
