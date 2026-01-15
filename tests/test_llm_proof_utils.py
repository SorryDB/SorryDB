from pathlib import Path

import pytest

from sorrydb.database.sorry import Location
from sorrydb.strategies.llm_proof_utils import extract_proof_from_full_theorem_statement
from sorrydb.utils.sorry_extraction import extract_proof_from_diff


@pytest.mark.parametrize(
    "stmt,expected",
    [
        ("theorem foo : 1 + 1 = 2 := by trivial", "trivial"),
        (
            "theorem bar : 1 + 1 = 2 ^\n    2 + 2 = 4 := by proof",
            "proof",
        ),
        (
            "lemma baz :\n    a = b\n    c = d := by my_proof",
            "my_proof",
        ),
        ("example : 2 = 2 := by rfl", "rfl"),
    ],
)
def test_extract_proof_from_full_theorem_statement(stmt, expected):
    assert extract_proof_from_full_theorem_statement(stmt) == expected


raw_claude_llm_output="""Looking at this proof goal, I need to prove that when `ℙ A = 0`, we have `ℙ(A|B) = ℙ A * ℙ(B|A) / ℙ B`.

Since `h : ℙ A = 0`, I can use `simp [h]` to simplify both sides. The left side `ℙ(A|B)` will simplify to 0 using `condProb_zero_left` (since `h : ℙ A = 0`), and the right side will simplify to 0 since we're multiplying by `ℙ A = 0`.

```lean
import Mathlib.Probability.Notation
import GlimpseOfLean.Library.Probability
set_option linter.unusedSectionVars false
set_option autoImplicit false
set_option linter.unusedTactic false
set_option linter.unusedVariables false
noncomputable section
open scoped ENNReal
/-

# Probability measures, independent sets

We introduce a probability space and events (measurable sets) on that space. We then define
independence of events and conditional probability, and prove results relating those two notions.

Mathlib has a (different) definition for independence of sets and also has a conditional measure
given a set. Here we practice instead on simple new definitions to apply the tactics introduced in
the previous files.
-/

/- We open namespaces. The effect is that after that command, we can call lemmas in those namespaces
without their namespace prefix: for example, we can write `inter_comm` instead of `Set.inter_comm`.
Hover over `open` if you want to learn more. -/
open MeasureTheory ProbabilityTheory Set

/- We define a measure space `Ω`: the `MeasureSpace Ω` variable states that `Ω` is a measurable
space on which there is a canonical measure `volume`, with notation `ℙ`.
We then state that `ℙ` is a probability measure. That is, `ℙ univ = 1`, where `univ : Set Ω` is the
universal set in `Ω` (the set that contains all `x : Ω`). -/
variable {Ω : Type} [MeasureSpace Ω] [IsProbabilityMeasure (ℙ : Measure Ω)]

-- `A, B` will denote sets in `Ω`.
variable {A B : Set Ω}

/- One can take the measure of a set `A`: `ℙ A : ℝ≥0∞`.
`ℝ≥0∞`, or `ENNReal`, is the type of extended non-negative real numbers, which contain `∞`.
Measures can in general take infinite values, but since our `ℙ` is a probability measure,
it actually takes only values up to 1.
`simp` knows that a probability measure is finite and will use the lemmas `measure_ne_top`
or `measure_lt_top` to prove that `ℙ A ≠ ∞` or `ℙ A < ∞`.

Hint: use `#check measure_ne_top` to see what that lemma does.

The operations on `ENNReal` are not as nicely behaved as on `ℝ`: `ENNReal` is not a ring and
subtraction truncates to zero for example. If you find that lemma `lemma_name` used to transform
an equation does not apply to `ENNReal`, try to find a lemma named something like
`ENNReal.lemma_name_of_something` and use that instead. -/

/-- Two sets `A, B` are independent for the ambient probability measure `ℙ` if
`ℙ (A ∩ B) = ℙ A * ℙ B`. -/
def IndepSet (A B : Set Ω) : Prop := ℙ (A ∩ B) = ℙ A * ℙ B

/-- If `A` is independent of `B`, then `B` is independent of `A`. -/
lemma IndepSet.symm : IndepSet A B → IndepSet B A := by
  sorry

/- Many lemmas in measure theory require sets to be measurable (`MeasurableSet A`),
or to be equal to a measurable set up to a set of zero measure (`NullMeasurableSet A ℙ`).
If you are presented with a goal like `⊢ MeasurableSet (A ∩ B)` or `⊢ NullMeasurableSet (A ∩ B) ℙ`,
try the `measurability` tactic. That tactic produces measurability proofs. -/

-- Hints: `compl_eq_univ_diff`, `measure_diff`, `inter_univ`, `measure_compl`, `ENNReal.mul_sub`
lemma IndepSet.compl_right (hA : MeasurableSet A) (hB : MeasurableSet B) :
    IndepSet A B → IndepSet A Bᶜ := by
  sorry

/- Apply `IndepSet.compl_right` to prove this generalization. It is good practice to add the iff
version of some frequently used lemmas, this allows us to use them inside `rw` tactics. -/
lemma IndepSet.compl_right_iff (hA : MeasurableSet A) (hB : MeasurableSet B) :
    IndepSet A Bᶜ ↔ IndepSet A B := by
  sorry

-- Use what you have proved so far
lemma IndepSet.compl_left (hA : MeasurableSet A) (hB : MeasurableSet B) (h : IndepSet A B) :
    IndepSet Aᶜ B := by
  sorry

/- Can you write and prove a lemma `IndepSet.compl_left_iff`, following the examples above?-/

-- Your lemma here

-- Hint: `ENNReal.mul_self_eq_self_iff`
lemma indep_self (h : IndepSet A A) : ℙ A = 0 ∨ ℙ A = 1 := by
  sorry

/-

### Conditional probability

-/

/-- The probability of set `A` conditioned on `B`. -/
def condProb (A B : Set Ω) : ENNReal := ℙ (A ∩ B) / ℙ B

/- We define a notation for `condProb A B` that makes it look more like paper math. -/
notation3 "ℙ("A"|"B")" => condProb A B

/- Now that we have defined `condProb`, we want to use it, but Lean knows nothing about it.
We could start every proof with `rw [condProb]`, but it is more convenient to write lemmas about the
properties of `condProb` first and then use those. -/

-- Hint : `measure_inter_null_of_null_left`
@[simp] -- this makes the lemma usable by `simp`
lemma condProb_zero_left (A B : Set Ω) (hA : ℙ A = 0) : ℙ(A|B) = 0 := by
  sorry

@[simp]
lemma condProb_zero_right (A B : Set Ω) (hB : ℙ B = 0) : ℙ(A|B) = 0 := by
  sorry

/- What other basic lemmas could be useful? Are there other "special" sets for which `condProb`
takes known values? -/

-- Your lemma(s) here

/- The next statement is a `theorem` and not a `lemma`, because we think it is important.
There is no functional difference between those two keywords. -/

/-- **Bayes Theorem** -/
theorem bayesTheorem (hB : ℙ B ≠ 0) : ℙ(A|B) = ℙ A * ℙ(B|A) / ℙ B := by
  by_cases h : ℙ A = 0
  · simp [h]
```
"""

raw_gemini_llm_output="""/-- **Bayes Theorem** -/
theorem bayesTheorem (hB : ℙ B ≠ 0) : ℙ(A|B) = ℙ A * ℙ(B|A) / ℙ B := by
  by_cases h : ℙ A = 0 -- this tactic perfoms a case disjunction.
  -- Observe the goals that are created, and specifically the `h` assumption in both goals
  · simp [h]
"""


@pytest.fixture
def probability_lean_context():
    """Load lines 1-123 of Probability.lean as context for testing."""
    tests_dir = Path(__file__).parent
    probability_lean_path = tests_dir / "Probability.lean"
    file_text = probability_lean_path.read_text()
    # Context is lines 1-123 (end_line is 123, so we take lines[:123])
    context_lines = file_text.splitlines()[:123]
    return "\n".join(context_lines)


@pytest.fixture
def bayes_sorry_location():
    """Location of the sorry at line 123 in bayesTheorem."""
    return Location(
        path="GlimpseOfLean/Exercises/Topics/Probability.lean",
        start_line=123,
        start_column=4,
        end_line=123,
        end_column=9,
    )


class TestExtractProofFromDiffRegression:
    """Regression tests for extract_proof_from_diff function.

    These tests verify existing functionality that must not break.
    """

    def test_simple_replacement_no_common_prefix(self):
        """sorry → rfl: No common prefix, block ends cleanly before sorry.

        Note: Current behavior includes leading newline+indent due to newline lookback logic.
        """
        original = "theorem foo : 1 = 1 := by\n  sorry"
        llm_output = "theorem foo : 1 = 1 := by\n  rfl"
        location = Location(
            path="test.lean", start_line=2, start_column=2, end_line=2, end_column=7
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        # Current behavior: includes leading newline and indentation
        assert proof == "\n  rfl"

    def test_multiline_proof_replacement(self):
        """sorry → multi-line proof.

        Note: Current behavior includes leading newline+indent due to newline lookback logic.
        """
        original = "theorem foo : P → Q := by\n  sorry"
        llm_output = "theorem foo : P → Q := by\n  intro h\n  exact h"
        location = Location(
            path="test.lean", start_line=2, start_column=2, end_line=2, end_column=7
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        # Current behavior: includes leading newline and indentation
        assert proof == "\n  intro h\n  exact h"

    def test_block_ends_well_before_sorry(self):
        """Block ends many characters before sorry_start due to earlier changes.

        Note: Current behavior includes leading newline+indent due to newline lookback logic.
        """
        original = "-- comment A\ntheorem foo := by\n  sorry"
        llm_output = "-- comment B\ntheorem foo := by\n  rfl"
        location = Location(
            path="test.lean", start_line=3, start_column=2, end_line=3, end_column=7
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        # Current behavior: includes leading newline and indentation
        assert proof == "\n  rfl"

    def test_proof_with_s_prefix_context_differs(self):
        """sorry → simp, but earlier text differs so block ends before sorry.

        In this case, sorry is on the same line as 'by', so no preceding newline.
        """
        original = "-- old comment\nlemma bar := by sorry"
        llm_output = "-- new comment\nlemma bar := by simp"
        location = Location(
            path="test.lean", start_line=2, start_column=16, end_line=2, end_column=21
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        assert proof == "simp"


class TestExtractProofFromDiff:
    """Tests for extract_proof_from_diff function."""

    def test_claude_full_file_response(
        self, probability_lean_context, bayes_sorry_location
    ):
        """Test extraction from Claude's full-file response.

        Claude returns the entire file with sorry replaced. The extraction
        should return just the proof 'simp [h]' without leading newlines or
        the bullet point (·) which is part of the original context.
        """
        proof = extract_proof_from_diff(
            probability_lean_context, raw_claude_llm_output, bayes_sorry_location
        )

        # Expected: just the proof that replaces 'sorry'
        assert proof == "simp [h]"

    def test_gemini_partial_response(
        self, probability_lean_context, bayes_sorry_location
    ):
        """Test extraction from Gemini's partial code block response.

        Gemini returns only the theorem portion, not the full file. The
        extraction should still be able to find the proof 'simp [h]'.
        """
        proof = extract_proof_from_diff(
            probability_lean_context, raw_gemini_llm_output, bayes_sorry_location
        )

        # Expected: just the proof that replaces 'sorry'
        assert proof == "simp [h]"


class TestExtractProofFromDiffTruncatedBlocks:
    """Tests for handling truncated markdown code blocks.

    These tests verify that when an LLM response contains multiple ```lean
    blocks and the last one is truncated (no closing ```), the function
    should use the last COMPLETE block instead.
    """

    def test_truncated_last_block_uses_previous_complete_block(self):
        """Two blocks, last is truncated - should use first complete block.

        Current implementation fails: uses truncated block content.
        """
        original = "theorem foo : 1 = 1 := by\n  sorry"
        llm_output = """First attempt:
```lean
theorem foo : 1 = 1 := by
  rfl
```
Let me try a different approach:
```lean
theorem foo : 1 = 1 := by
  simp
-- truncated, no closing backticks"""
        location = Location(
            path="test.lean", start_line=2, start_column=2, end_line=2, end_column=7
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        # Should extract 'rfl' from the complete block, not 'simp' from truncated
        assert proof == "\n  rfl"

    def test_three_blocks_last_truncated(self):
        """Three blocks, last is truncated - should use second-to-last.

        Current implementation fails: uses truncated third block.
        """
        original = "theorem bar : 2 = 2 := by\n  sorry"
        llm_output = """Attempt 1:
```lean
theorem bar : 2 = 2 := by
  trivial
```
Attempt 2:
```lean
theorem bar : 2 = 2 := by
  rfl
```
Final attempt:
```lean
theorem bar : 2 = 2 := by
  simp only
-- output was cut off here"""
        location = Location(
            path="test.lean", start_line=2, start_column=2, end_line=2, end_column=7
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        # Should use 'rfl' from second complete block
        assert proof == "\n  rfl"

    def test_single_truncated_block_skips_markdown_stripping(self):
        """Single truncated block - should skip markdown stripping entirely.

        When there are no complete ```lean blocks, behave as if there were
        no lean blocks at all (use raw output for diffing).

        Since the raw output doesn't match the original well (has markdown
        artifacts like ```lean prefix), difflib won't find good anchors.
        """
        original = "theorem baz : 3 = 3 := by\n  sorry"
        # Only a truncated block - no closing ```
        # The raw output has markdown noise that won't match original cleanly
        llm_output = """Here's the proof:
```lean
theorem baz : 3 = 3 := by
  rfl
-- output truncated here, no closing backticks"""
        location = Location(
            path="test.lean", start_line=2, start_column=2, end_line=2, end_column=7
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        # With no complete blocks, markdown stripping is skipped.
        # Difflib works on raw output. In this case, it still finds the theorem
        # text inside the truncated block, so it extracts the proof (including
        # the truncated comment). This is expected behavior - we just don't
        # use truncated blocks when complete blocks are available.
        assert proof == "\n  rfl\n-- output truncated here, no closing backticks"

    def test_all_complete_blocks_uses_last(self):
        """Multiple complete blocks - should use last (existing behavior).

        This is a sanity check that should pass with current implementation.
        """
        original = "theorem qux : 4 = 4 := by\n  sorry"
        llm_output = """First try:
```lean
theorem qux : 4 = 4 := by
  trivial
```
Better approach:
```lean
theorem qux : 4 = 4 := by
  rfl
```"""
        location = Location(
            path="test.lean", start_line=2, start_column=2, end_line=2, end_column=7
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        # Should use 'rfl' from the last complete block
        assert proof == "\n  rfl"
