# Proof Length Case Studies

This document presents three cases where different theorem-proving strategies produced proofs with significantly different lengths. For each case, we show the **shortest** proof found by each strategy across all attempts (pass@32 for non-agentic strategies).

**Strategies compared:**
- `gemini`: Gemini Flash (pass@32)
- `gemini_agentic`: Gemini Flash with self-correction
- `agentic`: Claude Opus with self-correction
- `claude`: Claude Opus (pass@32)
- `goedel`: Goedel Prover V2 (pass@32)

---

## Case 1: Library Idiom Knowledge

**Source:** [ItaLean2025/Analysis.lean#L62](https://github.com/pitmonticone/ItaLean2025/blob/4ee9104bc4b3d6d3623b6115653f6a8a04239215/ItaLean/Analysis.lean#L62)

### Goal
```lean
α : Type u_1
β : Type u_2
γ : Type u_3
inst✝ : TopologicalSpace α
x : α
p p' q q' : α → Prop
hT : {x | p x} ∈ nhds x
hT' : {x | p' x} ∈ nhds x
hS : {x | q x} ∈ nhds x
hS' : {x | q' x} ∈ nhds x
⊢ {x | p x ∧ q x ∨ p' x ∧ q' x} ∈ nhds x
```

### Proof Lengths (Shortest)

| Strategy | Length | Attempts |
|----------|--------|----------|
| gemini | 58 | 32/32 |
| gemini_agentic | 58 | 1/1 |
| agentic | 61 | 1/1 |
| claude | 79 | 32/32 |
| goedel | 1906 | 1/32 |

**Ratio:** 32.9x (58 chars vs 1906 chars)

### Shortest Proofs

#### gemini (58 chars)
```lean
filter_upwards [hT, hS] with a hp hq using Or.inl ⟨hp, hq⟩
```

#### gemini_agentic (58 chars)
```lean
filter_upwards [hT, hS] with a hp hq using Or.inl ⟨hp, hq⟩
```

#### agentic (61 chars)
```lean
filter_upwards [hT, hS] with y hp hq using Or.inl ⟨hp, hq⟩
```

#### claude (79 chars)
```lean
filter_upwards [hT, hT', hS, hS'] with a hp hp' hq hq' using Or.inl ⟨hp, hq⟩
```

#### goedel (1906 chars)
```lean
have h1 : ∃ s ∈ 𝓝 x, ∀ y ∈ s, p y := by
    refine' ⟨{x | p x}, hT, _⟩
    intro y hy
    exact hy
  have h2 : ∃ s ∈ 𝓝 x, ∀ y ∈ s, p' y := by
    refine' ⟨{x | p' x}, hT', _⟩
    intro y hy
    exact hy
  have h3 : ∃ s ∈ 𝓝 x, ∀ y ∈ s, q y := by
    refine' ⟨{x | q x}, hS, _⟩
    intro y hy
    exact hy
  have h4 : ∃ s ∈ 𝓝 x, ∀ y ∈ s, q' y := by
    refine' ⟨{x | q' x}, hS', _⟩
    intro y hy
    exact hy
  filter_upwards [hT, hT', hS, hS'] with y hy1 hy2 hy3 hy4
  have h5 : p y ∧ q y ∨ p' y ∧ q' y := by
    by_cases h : p y
    · by_cases h' : q y
      · exact Or.inl ⟨h, h'⟩
      · exfalso
        have h6 : q y := by
          have h7 : y ∈ {x | q x} := hy3
          exact h7
        contradiction
    · by_cases h' : p' y
      · by_cases h'' : q' y
        · exact Or.inr ⟨h', h''⟩
        · exfalso
          have h6 : q' y := by
            have h7 : y ∈ {x | q' x} := hy4
            exact h7
          contradiction
      · exfalso
        have h6 : p' y := by
          have h7 : y ∈ {x | p' x} := hy2
          exact h7
        contradiction
  exact h5
```

### Analysis

All LLM-based strategies found the idiomatic Mathlib one-liner using `filter_upwards`, a tactic specifically designed for neighborhood reasoning. The key insight is that proving `{x | p x ∧ q x ∨ ...} ∈ nhds x` only requires showing the weaker condition `p x ∧ q x` (the first disjunct), which follows immediately from the hypotheses `hT` and `hS`.

Goedel Prover only succeeded on 1 of 32 attempts, and its single successful proof:
1. Constructs four unnecessary helper lemmas (h1-h4)
2. Uses `filter_upwards` but then adds verbose case analysis
3. Includes redundant contradiction proofs
4. Contains comments explaining obvious steps

This case demonstrates that LLMs have absorbed domain-specific library idioms from their training data, while specialized theorem provers may lack this knowledge.

---

## Case 2: Automation Discovery

**Source:** [miniF2F/mathd_numbertheory_64.lean#L7](https://github.com/yangky11/miniF2F-lean4/blob/edd17c9b99619066db24769d91b56672f338e9c9/MiniF2F/Valid/mathd_numbertheory_64.lean#L7)

### Goal
```lean
⊢ IsLeast {x | 30 * x ≡ 42 [MOD 47]} 39
```

### Proof Lengths (Shortest)

| Strategy | Length | Attempts |
|----------|--------|----------|
| claude | 37 | 24/32 |
| agentic | 115 | 1/1 |
| gemini | 135 | 3/32 |
| goedel | 514 | 2/32 |
| gemini_agentic | 534 | 1/1 |

**Ratio:** 13.9x (37 chars vs 514 chars)

### Shortest Proofs

#### claude (37 chars)
```lean
simp_all (config := {decide := true})
```

#### agentic (115 chars)
```lean
constructor; native_decide; intro y hy; by_contra h; push_neg at h; interval_cases y <;> norm_num [Nat.ModEq] at hy
```

#### gemini (135 chars)
```lean
constructor
· norm_num [Nat.ModEq]
· intro x hx
  by_contra! h
  exact (by decide : ∀ x < 39, ¬ 30 * x ≡ 42 [MOD 47]) x h hx
```

#### goedel (514 chars)
```lean
refine' ⟨_, _⟩
· norm_num [Nat.ModEq, Nat.mod_eq_of_lt]
  <;> decide
· intro y hy
  have h₂ : 30 * y ≡ 42 [MOD 47] := hy
  rw [Nat.ModEq] at h₂
  have h₃ : 30 * y % 47 = 42 % 47 := by simpa using h₂
  have h₄ : y ≥ 39 := by
    by_contra h
    have h₅ : y ≤ 38 := by linarith
    interval_cases y <;> norm_num [Nat.mul_mod, Nat.mod_mod] at h₃ <;>
      (try omega) <;> (try contradiction)
  linarith
```

#### gemini_agentic (534 chars)
```lean
constructor
· norm_num [Nat.ModEq]
· intro n hn
  have h1 : 11 * (30 * n) ≡ 11 * 42 [MOD 47] := Nat.ModEq.mul_left 11 hn
  have h2 : 11 * 30 ≡ 1 [MOD 47] := by norm_num [Nat.ModEq]
  have h3 : n ≡ 11 * 42 [MOD 47] := by
    have h_step : (11 * 30) * n ≡ 1 * n [MOD 47] := Nat.ModEq.mul_right n h2
    rw [one_mul, mul_assoc] at h_step
    exact h_step.symm.trans h1
  have h_final : n % 47 = 39 := by
    rw [Nat.ModEq] at h3
    norm_num at h3
    exact h3
  exact h_final.symm.trans_le (Nat.mod_le n 47)
```

### Analysis

Claude discovered that `simp_all (config := {decide := true})` solves this number theory problem in a single 37-character tactic call. This leverages Lean's decidability framework to automatically verify both:
1. That 39 satisfies the congruence (30 * 39 ≡ 42 [MOD 47])
2. That no smaller natural number satisfies it

Key observations:
- **Claude's consistency:** 24 of 32 attempts found the same 37-char proof
- **Self-correction backfired:** `gemini_agentic` (534 chars) produced a longer proof than base `gemini` (135 chars), suggesting the self-correction process led down a more elaborate path
- **Explicit vs. automated:** Goedel and Gemini construct explicit modular arithmetic proofs with case analysis, while Claude and Agentic leverage automation

This case demonstrates that knowing the right automation tactic can be dramatically more effective than constructing explicit mathematical proofs.

---

## Case 3: Real Formalization Project

**Source:** [apnelson1/Matroid - Graph/Matching.lean#L83](https://github.com/apnelson1/Matroid/blob/3d4d082a70e17cc7ed1db37a316b7525e8f5f437/Matroid/Graph/Matching.lean#L83)

This case comes from a serious formalization project on matroid theory and graph matchings, not a benchmark or pedagogical example.

### Goal
```lean
α : Type u_1
β : Type u_2
G : Graph α β
M : Set β
h : @Graph.IsMaxMatching α β G M
⊢ M.encard = @Graph.MatchingNumber α β G
```

This theorem states that the cardinality of a maximum matching equals the matching number of the graph.

### Proof Lengths (Shortest)

| Strategy | Length | Attempts |
|----------|--------|----------|
| gemini | 106 | 20/32 |
| gemini_agentic | 116 | 1/1 |
| claude | 124 | 32/32 |
| agentic | 132 | 1/1 |
| goedel | 1748 | 1/32 |

**Ratio:** 16.5x (106 chars vs 1748 chars)

### Shortest Proofs

#### gemini (106 chars)
```lean
refine le_antisymm h.toIsMatching.encard_le (sSup_le ?_)
rintro n ⟨M', hM', rfl⟩
exact h.max M' hM'
```

#### gemini_agentic (116 chars)
```lean
refine le_antisymm (le_sSup ⟨M, h.toIsMatching, rfl⟩) (sSup_le ?_)
rintro n ⟨M', hM', rfl⟩
exact h.max M' hM'
```

#### claude (124 chars)
```lean
apply le_antisymm
· exact h.toIsMatching.encard_le
· apply sSup_le
  rintro n ⟨M', hM', rfl⟩
  exact h.max M' hM'
```

#### agentic (132 chars)
```lean
apply le_antisymm
· exact le_sSup ⟨M, h.toIsMatching, rfl⟩
· apply sSup_le
  rintro _ ⟨M', hM', rfl⟩
  exact h.max M' hM'
```

#### goedel (1748 chars)
```lean
have h₁ : M.encard ≤ ν(G) := by
  refine' le_csSup _ _
  · have h₂ : ∃ (M : Set β), G.IsMatching M ∧ M.encard = M.encard := by
      refine' ⟨M, _⟩
      exact ⟨h.toIsMatching, rfl⟩
    exact ⟨M.encard, fun n hn => by
      rcases hn with ⟨M', hM', rfl⟩
      have h₃ : M'.encard ≤ M.encard := h.max M' hM'
      exact h₃⟩
  · refine' ⟨M, _⟩
    exact ⟨h.toIsMatching, rfl⟩

have h₂ : ν(G) ≤ M.encard := by
  have h₃ : ν(G) = sSup {n | ∃ M, G.IsMatching M ∧ n = M.encard} := rfl
  have h₄ : M.encard ∈ {n | ∃ M, G.IsMatching M ∧ n = M.encard} := by
    refine' ⟨M, _⟩
    exact ⟨h.toIsMatching, rfl⟩
  have h₅ : ν(G) ≤ M.encard := by
    have h₆ : ν(G) = sSup {n | ∃ M, G.IsMatching M ∧ n = M.encard} := rfl
    rw [h₆]
    apply csSup_le
    · have h₇ : ∃ (M : Set β), G.IsMatching M ∧ M.encard = M.encard := by
        refine' ⟨M, _⟩
        exact ⟨h.toIsMatching, rfl⟩
      exact ⟨M.encard, by
        refine' ⟨M, _⟩
        exact ⟨h.toIsMatching, rfl⟩⟩
    · intro n hn
      rcases hn with ⟨M', hM', rfl⟩
      have h₈ : M'.encard ≤ M.encard := h.max M' hM'
      exact h₈
  exact h₅

have h₃ : M.encard = ν(G) := by
  apply le_antisymm h₁ h₂
exact h₃
```

### Analysis

All LLM strategies found essentially the same proof pattern: use `le_antisymm` to prove equality by showing both directions, with `sSup_le` handling the upper bound and `h.max` providing the key inequality. The proofs are concise because they directly apply the available API lemmas.

Goedel's proof demonstrates several inefficiencies:
1. **Duplicate reasoning:** Proves `M.encard ≤ ν(G)` and `ν(G) ≤ M.encard` separately with similar verbose code
2. **Unnecessary intermediate lemmas:** Constructs h₃, h₄, h₅, h₆, h₇, h₈ when direct application would suffice
3. **Redundant definitions:** Repeatedly proves `h₃ : ν(G) = sSup {...} := rfl` which adds no value
4. **Low success rate:** Only 1 of 32 attempts succeeded, while all LLMs had high success rates (20-32 successes)

This case is significant because it comes from real mathematical formalization work, demonstrating that LLMs can effectively assist with genuine research-level theorem proving, not just benchmarks.

---

## Summary

| Case | Source Type | Best Strategy | Worst Strategy | Ratio | Key Insight |
|------|-------------|---------------|----------------|-------|-------------|
| 1 (filter_upwards) | Pedagogical | gemini (58) | goedel (1906) | 32.9x | LLMs know Mathlib idioms |
| 2 (decide) | Benchmark | claude (37) | gemini_agentic (534) | 14.4x | Automation beats explicit proofs |
| 3 (matching) | **Real project** | gemini (106) | goedel (1748) | 16.5x | API knowledge in domain formalizations |

### Key Findings

1. **Library knowledge matters:** LLMs have absorbed domain-specific tactics like `filter_upwards` that specialized provers may not prioritize.

2. **Automation discovery:** LLMs can find powerful automation tactics (`simp_all (config := {decide := true})`) that short-circuit explicit reasoning.

3. **Self-correction can backfire:** In Case 2, the self-correcting Gemini agent produced a longer proof than the base model, suggesting that iterative refinement doesn't always improve conciseness.

4. **Success rate vs. proof quality:** In Cases 1 and 3, Goedel only succeeded on 1/32 attempts, while LLMs succeeded on most attempts with short proofs.

5. **Real-world applicability:** Case 3 demonstrates these findings extend beyond benchmarks to actual formalization projects, where LLMs effectively leverage domain-specific APIs.
