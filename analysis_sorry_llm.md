# SorryDB Benchmark — LLM Validity Analysis

**Model:** `claude-haiku-4-5-20251001`  |  **Sorries analysed:** 1000

This report addresses the reviewer's concern about whether sorry instances
represent meaningful standalone proof obligations.

---

## 1. Validity Distribution

| Validity | Count | Percent | Description |
| --- | --- | --- | --- |
| standalone | 373 | 37.3% | Clear self-contained proof obligation |
| trivial | 54 | 5.4% | Likely one basic tactic (rfl, simp, decide, …) |
| needs_auxiliary | 327 | 32.7% | Solvable but likely needs a helper lemma |
| needs_refactoring | 100 | 10.0% | Proof structure needs to change first |
| placeholder_false | 135 | 13.5% | Known-false or intentional placeholder |
| unclear | 11 | 1.1% | Insufficient context to judge |

**673 / 1000 (67.3%) sorries have no unsolvable indicator** — i.e. the LLM found no evidence in the goal or surrounding source that would prevent a prover from attempting them.

---

## 2. Difficulty Distribution

| Difficulty | Count | Percent |
| --- | --- | --- |
| trivial | 105 | 10.5% |
| easy | 112 | 11.2% |
| medium | 309 | 30.9% |
| hard | 471 | 47.1% |

---

## 3. Validity by Repository Category

| Category | Total | Standalone/Trivial | % Solo | Needs Auxiliary | Needs Refactor | Placeholder |
| --- | --- | --- | --- | --- | --- | --- |
| benchmark | 48 | 24 | 50% | 20 | 2 | 2 |
| formalization | 562 | 174 | 31% | 237 | 57 | 86 |
| library | 89 | 51 | 57% | 21 | 9 | 8 |
| pedagogical | 216 | 141 | 65% | 39 | 17 | 18 |
| tooling | 85 | 37 | 44% | 10 | 15 | 21 |
| TOTAL | 1000 | 427 | 43% | 327 | 100 | 135 |

---

## 4. Sample Sorries by Validity Class

### `standalone`

**Goal:**
```
𝕜 : Type u_3  
  α : Type u_4  
  mα : MeasurableSpace α  
  inst✝² : DiscreteMeasurableSpace α  
  inst✝¹ : Fintype α  
  inst✝ : RCLike 𝕜  
  f g : α → 𝕜  
  p q r : NNReal  
  hr₀ : some r ≠ 0  
  hpqr : ENNReal.HolderTriple (some p) (some q) (some r)  
  ⊢ p ≠ 0
```
**Key observation:** Derive non-zero constraint on p from HolderTriple property definition or library lemma.
**Reasoning:** The goal `p ≠ 0` follows from the hypothesis `hpqr : ENNReal.HolderTriple (some p) (some q) (some r)`. The HolderTriple condition constrains the exponents to be non-zero. This requires understanding the definition/properties of HolderTriple and possibly unfolding it or finding a relevant lemma in the library.
**URL:** https://github.com/YaelDillies/LeanAPAP/blob/96325adf1d139b2adaa32d9839f096eec959480d/LeanAPAP/Prereqs/Inner/Hoelder/Compact.lean#L99

**Goal:**
```
S : Set ℝ  
  M : ℝ  
  hM : RealAnalysisGame.IsUB S M  
  s₀ : ℝ  
  hs₀ : s₀ ∈ S  
  ab : (n : ℕ) → { p // p.1 ∈ S ∧ RealAnalysisGame.IsUB S p.2 ∧ p.1 ≤ p.2 ∧ p.2 - p.1 ≤ (M - s₀) / 2 ^ n } :=  
    fun n =>  
      Nat.recAux ⟨(s₀, M), ⋯⟩  
        (fun n hn =>  
          let hp := ⋯;  
          let p := ↑hn;  
          let mid := (p.1 …
```
**Key observation:** In the else branch (no element in S above midpoint), the algorithm updates left endpoint to left endpoint; requires unfolding ab's recursive definition.
**Reasoning:** The goal is to prove a(n+1) = a(n) in the else branch where there's no element in S ≥ (a(n) + b(n))/2. This requires unfolding the definition of a(n+1) and reasoning about the recursive construction of the ab sequence, which involves understanding how the midpoint bisection works.
**URL:** https://github.com/AlexKontorovich/RealAnalysisGame/blob/26963c3700b2b6cc66e605e0826977f9a4a0be94/Game/Levels/L24Levels/L03.lean#L138

**Goal:**
```
α : Type  
  hα : OracleComp.SampleableType α  
  n : ℕ  
  hn : NeZero n  
  x y : Fin n  
  ⊢ Pr[=x | ⋯ ▸ OracleComp.uniformSample (Fin (n - 1 + 1)) (OracleComp.instSampleableTypeFinHAddNatOfNat (n - 1))] =  
      Pr[=y | ⋯ ▸ OracleComp.uniformSample (Fin (n - 1 + 1)) (OracleComp.instSampleableTypeFinHAddNatOfNat (n - 1…
```
**Key observation:** Uniform sampling probabilities must be equal for distinct elements in a finite type.
**Reasoning:** The goal requires proving that uniform probability distributions yield equal probabilities for any two elements from a finite type. This is a standard property of uniform sampling where all elements are equiprobable. The goal involves reasoning about probability expressions with implicit casting and finiteness constraints.
**URL:** https://github.com/Verified-zkEVM/VCV-io/blob/2049180482d07341e984f723c047d6d030a839bb/VCVio/OracleComp/Constructions/UniformSelect.lean#L381

### `needs_auxiliary`

**Goal:**
```
n : ℕ  
  f : GlobalTheorem.E✝ n → ℝ  
  fc : ContDiff ℝ 2 f  
  x y : GlobalTheorem.E✝ n  
  ε : ℝ  
  hε : ε > 0  
  hdiff : failed to pretty print expression (use 'set_option pp.rawOnError true' for raw representation)  
  mpb : mixed_partials_bounded f x  
  g₀ : ℝ → GlobalTheorem.E✝ n := GlobalTheorem.interpolator✝ n x y  
  g : …
```
**Key observation:** Bound g'(0) by ε times sum of absolute partial derivatives using chain rule and interpolation.
**Reasoning:** The goal requires bounding |g' 0| using ε and partial derivatives. The context provides mixed_partials_bounded and chain rule infrastructure, but no direct auxiliary lemmas about bounds from interpolated derivatives. Likely requires proving intermediate bounds connecting g' 0 to directional derivatives and partial derivatives via Taylor expansion or mean value theorem arguments.
**URL:** https://github.com/jcreedcmu/Noperthedron/blob/05eb814bfe42f2d8ca0ef0c3e35be9e24761ddac/Noperthedron/Global/BoundedPartialsControlDifference.lean#L96

**Goal:**
```
case left  
  C : Type  
  inst✝¹ : Category.{0, 0} C  
  K : Type  
  inst✝ : DivisionRing K  
  M : CategoryTheory.Functor C (ModuleCat K)  
  I : @DirectSumDecomposition C inst✝¹ K inst✝ M  
  c : C  
  ⊢ iSupIndep fun p => ↑p c
```
**Key observation:** Part of `IsInternal` proof requiring pointwise independence of submodules in a direct sum decomposition.
**Reasoning:** The goal requires proving `iSupIndep` (independent supremum) for a family of submodules indexed by `I` at a specific point `c`. This is the first part of a two-constructor proof for `IsInternal`, which typically requires establishing both independence and that the supremum equals top. The independence property likely follows from the `DirectSumDecomposition` structure but needs appropriate lemmas about how independence is preserved pointwise.
**URL:** https://github.com/Paul-Lez/PersistentDecomp/blob/c36471055817ef5332e27b4f99654257f45c68d1/PersistentDecomp/DirectSumDecomposition.lean#L51

**Goal:**
```
α : Type u_1  
  mα : MeasurableSpace α  
  inst✝² : DecidableEq α  
  inst✝¹ : MeasurableSingletonClass α  
  alg : Algorithm α ℝ  
  ν : Kernel α ℝ  
  inst✝ : IsMarkovKernel ν  
  a b : α  
  hab : a ≠ b  
  ⊢ IndepFun (fun ω s => rewardByCount a s ω) (fun ω s => rewardByCount b s ω) (Bandit.measure alg ν)
```
**Key observation:** Independence of reward counts for distinct actions requires auxiliary independence lemmas about the underlying measure structure.
**Reasoning:** The goal requires proving independence of two reward counting functions for different actions in a Bandit algorithm context. While a lemma `identDistrib_rewardByCount_stream` exists (line 313-316) that characterizes the distribution of reward counts, establishing independence between rewards for distinct actions (hab : a ≠ b) likely requires additional helper lemmas connecting the measure structure to independence properties.
**URL:** https://github.com/RemyDegenne/lean-bandits/blob/1f786514e43b6305e3760c9779528cbc651c7cee/LeanBandits/RewardByCountMeasure.lean#L320

### `needs_refactoring`

**Goal:**
```
case succ  
  L : Logic ℕ  
  χ ξ : Formula ℕ  
  T : LO.Propositional.FTheory L  
  hT : χ ➝ ξ ∉ LO.Propositional.FTheory.theory L T  
  φ : Formula ℕ  
  hφ : φ ∈ LO.Propositional.FTheory.lindenbaum.construction_omega L χ ξ T hT  
  i : ℕ  
  ih :  
    φ ∈ LO.Propositional.FTheory.lindenbaum.construction L χ ξ T hT i →  
      χ ➝ φ ∈ …
```
**Key observation:** Inductive proof over lindenbaum construction requires case analysis on match_1 pattern; commented fallback suggests structural issues.
**Reasoning:** This sorry is in a case of an inductive proof where the induction hypothesis must be applied. However, the hypothesis `hi` involves a complex pattern-match over `construction.match_1`, which requires careful case analysis. The commented-out code suggests the original author struggled with this structure and may have discovered it needs refactoring. The proof requires understanding how the lindenbaum construction works and how to properly apply the match branches.
**URL:** https://github.com/FormalizedFormalLogic/Foundation/blob/7c74089c2442ee211abfa1e2dd5a75091800f57b/Foundation/Propositional/Kripke2/FTheory.lean#L116

**Goal:**
```
case hp  
  ι : Type u_1  
  inst✝ : UnitalFreeStateTheory ι  
  i : ι  
  ρ : MState (H i)  
  σ : (n : ℕ) → ↑IsFree  
  ε ε' : Prob  
  hε'₁ : 0 < ε'  
  hε'₂ : ε' < ε  
  hε : ε < 1  
  hR1R2 : @SteinsLemma.R1✝ ι inst✝ i ρ ε < @SteinsLemma.R2✝ ι inst✝ i ρ σ  
  hR1 : @SteinsLemma.R1✝ ι inst✝ i ρ ε ≠ ⊤  
  hR2 : @SteinsLemma.R2✝ ι inst✝ i ρ σ ≠…
```
**Key observation:** Comment indicates 46 goals created; tactic approach abandoned with blanket sorry statements.
**Reasoning:** The sorry at line 1451 is part of a multi-goal situation generated by `repeat rw [ENNReal.ofReal_add]` that produced 46 goals. The comments indicate confusion about why so many goals were generated and that even `positivity` doesn't fully resolve them (leaving 11 goals). The entire tactic block (lines 1450-1455) was abandoned, suggesting the approach needs restructuring rather than direct completion.
**URL:** https://github.com/Timeroot/Lean-QuantumInfo/blob/6099da24305d6ca71df680ccada8f91d026cb604/QuantumInfo/Finite/ResourceTheory/SteinsLemma.lean#L1455

**Goal:**
```
ι : Type  
  oSpec : OracleSpec ι  
  StmtIn WitIn StmtOut WitOut : Type  
  n : ℕ  
  pSpec : ProtocolSpec n  
  inst✝ : (i : pSpec.ChallengeIdx) → SampleableType (pSpec.Challenge i)  
  σ : Type  
  init : ProbComp σ  
  impl : QueryImpl oSpec (StateT σ ProbComp)  
  relIn : Set (StmtIn × WitIn)  
  relOut : Set (StmtOut × WitOut)  
  verif…
```
**Key observation:** Case analysis incomplete with `stop` statement and TODO comment suggesting major refactoring needed.
**Reasoning:** The surrounding proof context shows the author used `stop` (line 250) before attempting the case split on `n = 0`, indicating the original proof strategy was abandoned. The `sorry` at line 242 appears after a case analysis that may have the wrong structure. The TODO comment at line 245 confirms this is incomplete work in progress.
**URL:** https://github.com/Verified-zkEVM/ArkLib/blob/f04465d1faac1b46505a53fa5af90cfa223ad823/ArkLib/OracleReduction/Security/RoundByRound.lean#L250

### `placeholder_false`

**Goal:**
```
⊢ {a₁ |  
        ∃ a,  
          a 0 = a₁ ∧  
            ∀ (i : ℕ),  
              0 < a i ∧  
                3 ≤ (a i).properDivisors.card ∧  
                  a (i + 1) = (List.take 3 ((a i).properDivisors.sort fun x1 x2 => x1 ≤ x2).reverse).sum} =  
      IMO2025P4.answer
```
**Key observation:** IMO 2025 Problem 4 proof: must establish set equality for complex recurrence involving proper divisors.
**Reasoning:** This proof obligation requires computing the exact set of natural numbers satisfying a complex recurrence relation involving proper divisors (IMO 2025 Problem 4). The `answer` is defined as a `sorry` without explicit value, making this a placeholder proof. This is a genuine mathematical competition problem requiring creative problem-solving rather than straightforward automation.
**URL:** https://github.com/jsm28/IMOLean/blob/265ae0e596f743accb299efa89e265ff2b69aae1/IMO/IMO2025P4.lean#L18

**Goal:**
```
⊢ sorry ↔ IsRamseySizeLinear Erdos567.K33
```
**Key observation:** Structural placeholder for unsolved Erdős Problem 567; mathematical answer unknown.
**Reasoning:** This is an open research problem about Ramsey theory (Erdős Problem 567), specifically whether K₃,₃ is Ramsey size linear. The sorry on line 70 marks a direct statement of an open problem. The annotation @[category research open, AMS 05] indicates this is an open research question, not a solvable proof obligation.
**URL:** https://github.com/google-deepmind/formal-conjectures/blob/2d387cc191243cd74dcfdb3d4e281ead4c1ec4a2/FormalConjectures/ErdosProblems/567.lean#L70

**Goal:**
```
case hp  
  ι : Type u_1  
  inst✝ : UnitalFreeStateTheory ι  
  i : ι  
  ρ : MState (H i)  
  σ : (n : ℕ) → ↑IsFree  
  ε ε' : Prob  
  hε'₁ : 0 < ε'  
  hε'₂ : ε' < ε  
  hε : ε < 1  
  hR1R2 : @SteinsLemma.R1✝ ι inst✝ i ρ ε < @SteinsLemma.R2✝ ι inst✝ i ρ σ  
  hR1 : @SteinsLemma.R1✝ ι inst✝ i ρ ε ≠ ⊤  
  hR2 : @SteinsLemma.R2✝ ι inst✝ i ρ σ ≠…
```
**Key observation:** Placeholder sorry due to Lean version incompatibility with repeat rw [ENNReal.ofReal_add] generating 46 unprintable goals.
**Reasoning:** The comment explicitly states "It seems like this works(?) on later versions of Lean but not here...?" and "so for now I'm closing everything with sorry". This indicates the sorry is a temporary placeholder due to Lean version incompatibility (repeat rw [ENNReal.ofReal_add] produces 46 goals that cannot be easily closed), not a genuine proof obligation.
**URL:** https://github.com/Timeroot/Lean-QuantumInfo/blob/6099da24305d6ca71df680ccada8f91d026cb604/QuantumInfo/Finite/ResourceTheory/SteinsLemma.lean#L1455

### `trivial`

**Goal:**
```
case h.«1».«7»  
  i j : ℕ  
  hi1 : 1 ≤ 1  
  hi2 : 1 ≤ 8  
  hj1 : 1 ≤ 7  
  hj2 : 7 ≤ 8  
  hij1 : ⟨1, ⋯⟩ < ⟨7, ⋯⟩  
  hij2 : 2 * ↑⟨7, ⋯⟩ - ↑⟨1, ⋯⟩ ∈ Set.Icc 1 8  
  hc1 :  
    (@Bulgaria1998P1.coloring_of_eight.match_1 8 (fun x => Fin 2) ⟨1, ⋯⟩ (fun property => 0) (fun property => 1)  
        (fun property => 0) (fun property => 1) …
```
**Key observation:** After case analysis, coloring values at positions 1 and 7 must be unequal and equal simultaneously—a contradiction proved by comparing hc1 and hc2.
**Reasoning:** The goal is `False` after unfolding the coloring definition and case-analyzing all pairs (i,j) from the set {1..8}. The hypotheses hc1 and hc2 establish contradictory equalities between coloring values at different points, making the goal trivially false. A single tactic like `exact absurd hc1 hc2` or `contradiction` should close this.
**URL:** https://github.com/dwrensha/compfiles/blob/a2ff4bb1396c3bc8047103a0a45a00e2c57571c4/Compfiles/Bulgaria1998P1.lean#L75

**Goal:**
```
α : Type u_1  
  l1 l2 : List α  
  elt : α  
  idx : ℕ  
  hidx : idx ≤ l1.length  
  ⊢ idx = 0
```
**Key observation:** After nil case match, idx must equal 0 due to length constraint on empty list.
**Reasoning:** The goal `idx = 0` follows directly from the hypothesis `idx ≤ l1.length` where `l1 = []` (nil case). Since the list is empty, its length is 0, so `idx ≤ 0` forces `idx = 0`. This is a straightforward application of `omega` or similar tactics.
**URL:** https://github.com/VCA-EPFL/graphiti/blob/3285ca701a33477bbd2a3ac954584439d80db747/Graphiti/Projects/Noc/Utils.lean#L203

**Goal:**
```
α : Type  
  hα : OracleComp.SampleableType α  
  n : ℕ  
  ⊢ Pr[⊥ | $[0..n]] = 0
```
**Key observation:** Probability of failure for uniformFin is always zero; standard property should be derivable.
**Reasoning:** The goal states that the probability of failure for a uniform sample from a finite range [0..n] is 0. This is a basic property of the uniformFin sampler - it cannot fail since the range is always nonempty. A single `simp` tactic with the appropriate lemmas should suffice.
**URL:** https://github.com/Verified-zkEVM/VCV-io/blob/2049180482d07341e984f723c047d6d030a839bb/VCVio/OracleComp/Constructions/UniformSelect.lean#L369

### `unclear`

**Goal:**
```
p : ℕ  
  inst✝¹ : Fact (Nat.Prime p)  
  n : ℕ  
  hn : NeZero n  
  inst✝ : NonEmptyProvableType (fields n)  
  hnout : 2 ^ (n + 1) < p  
  ⊢ failed to pretty print expression (use 'set_option pp.rawOnError true' for raw representation)
```
**Key observation:** Goal fails to pretty-print; cannot determine proof obligation validity or meaning.
**Reasoning:** The goal cannot be pretty-printed, indicating a serious issue with the expression itself—either malformed, referencing undefined identifiers, or containing type errors. This prevents meaningful analysis of what needs to be proven. Without a valid goal, the sorry cannot be classified as standalone or assessed for solvability.
**URL:** https://github.com/Verified-zkEVM/clean/blob/6dfafe27ea1e733e1e7f01610a63789772eccec6/Clean/Circomlib/BinSub.lean#L131

**Goal:**
```
case mk.cons  
  a : Type  
  bs : List a  
  n : a  
  ns : List a  
  ok :  
    ((n :: ns).isEmpty = true → bs.isEmpty = true ∨ bs.length = 1) ∧  
      (bs.isEmpty = true → (n :: ns).isEmpty = true ∨ (n :: ns).length = 1)  
  ⊢ failed to pretty print expression (use 'set_option pp.rawOnError true' for raw representation)
```
**Key observation:** Goal cannot be pretty-printed; unprintable goals suggest corruption or unsupported structures.
**Reasoning:** The goal pretty-printer has failed, making it impossible to determine what needs to be proven. The hypothesis `ok` concerns relationships between list properties (isEmpty, length) for the SymList structure, but without seeing the actual goal, any classification is speculative. The context suggests a proof about SymList initialization is incomplete.
**URL:** https://github.com/arademaker/fad/blob/ac40e4faf3b1252bc943676314449c22b5af3c9d/Fad/Assignment03.lean#L81

**Goal:**
```
n : ℕ  
  net : BiasedHopfieldNetwork n  
  ⊢ failed to pretty print expression (use 'set_option pp.rawOnError true' for raw representation)
```
**Key observation:** Goal contains pretty-printing error; actual obligation unclear without raw representation.
**Reasoning:** The goal cannot be displayed due to a pretty-printing error, making it impossible to assess the actual proof obligation. The comment suggests this requires similar reasoning to the regular Hopfield network convergence proof, which is typically a complex argument involving energy monotonicity and finite state space finiteness. The goal state is malformed.
**URL:** https://github.com/or4nge19/NeuralNetworks/blob/7ccc7b6b1186e9b5404f9b6001597679b0bb705c/NeuralNetworks/Hopfield/Biased.lean#L127

---

## 5. Key Takeaways for Reviewer Response

- **373 (37%) sorries** are classified as *standalone* proof obligations — clear mathematical statements with sufficient local context for an automated prover to attempt.

- **54 (5%) sorries** are flagged as *trivial* (e.g. `rfl`, `simp`, `decide`). These serve as easy benchmarks that calibrate what a basic tactic solver can handle.

- **Only 135 (13.5%) sorries** appear to be known-false or intentional placeholders, confirming the benchmark is not dominated by unsolvable tasks.

- **327 (32.7%) sorries** likely require auxiliary lemmas — this represents a meaningful sub-task for systems that can decompose proof obligations.

- **327 (32.7%) sorries** have some unsolvable indicator. Even if excluded, the remaining **673** sorries form a challenging and diverse benchmark.
