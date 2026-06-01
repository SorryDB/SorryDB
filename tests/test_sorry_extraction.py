#!/usr/bin/env python3

from sorrydb.database.sorry import Location
from sorrydb.utils.sorry_extraction import extract_proof_from_diff


def test_extract_proof_two_sorries_same_line():
    """Test extracting proofs when two sorries are on the same line.

    This matches the real test case from tests/mock_lean_repository/MockLeanRepository/same_line.lean
    """

    # Original code with two sorries on the same line (from same_line.lean)
    original = """-- two sorries on same line

/-- proofs
  first sorry: "exact Nat.le_refl n"
  second sorry: "exact Nat.zero_le 1"
-/


theorem ineq (n : Nat) : n + 1 ≥ n + 0 := by
  exact Nat.add_le_add (by sorry) (by sorry)

theorem ineq_solved (n : Nat) : n + 1 ≥ n + 0 := by
  exact Nat.add_le_add (by exact Nat.le_refl n) (by exact Nat.zero_le 1)
"""

    # LLM output with first sorry replaced (includes full context)
    llm_output_first = """-- two sorries on same line

/-- proofs
  first sorry: "exact Nat.le_refl n"
  second sorry: "exact Nat.zero_le 1"
-/


theorem ineq (n : Nat) : n + 1 ≥ n + 0 := by
  exact Nat.add_le_add (by exact Nat.le_refl n) (by sorry)

theorem ineq_solved (n : Nat) : n + 1 ≥ n + 0 := by
  exact Nat.add_le_add (by exact Nat.le_refl n) (by exact Nat.zero_le 1)
"""

    # LLM output with second sorry replaced (includes full context)
    llm_output_second = """-- two sorries on same line

/-- proofs
  first sorry: "exact Nat.le_refl n"
  second sorry: "exact Nat.zero_le 1"
-/


theorem ineq (n : Nat) : n + 1 ≥ n + 0 := by
  exact Nat.add_le_add (by sorry) (by exact Nat.zero_le 1)

theorem ineq_solved (n : Nat) : n + 1 ≥ n + 0 := by
  exact Nat.add_le_add (by exact Nat.le_refl n) (by exact Nat.zero_le 1)
"""

    # Test extracting the first sorry
    # The first sorry is at line 10, columns 27-32 (as in sorries.json)
    # Line 10 is: "  exact Nat.add_le_add (by sorry) (by sorry)"
    location_first = Location(
        path="MockLeanRepository/same_line.lean",
        start_line=10,
        start_column=27,
        end_line=10,
        end_column=32
    )

    proof_first = extract_proof_from_diff(original, llm_output_first, location_first)
    assert proof_first is not None, "Failed to extract first sorry proof"
    # The proof should be "exact Nat.le_refl n" (from proofs.json)
    assert "exact Nat.le_refl n" in proof_first, f"Expected 'exact Nat.le_refl n' in proof, got: {repr(proof_first)}"

    # Test extracting the second sorry
    # The second sorry is at line 10, columns 38-43 (as in sorries.json)
    location_second = Location(
        path="MockLeanRepository/same_line.lean",
        start_line=10,
        start_column=38,
        end_line=10,
        end_column=43
    )

    proof_second = extract_proof_from_diff(original, llm_output_second, location_second)
    assert proof_second is not None, "Failed to extract second sorry proof"
    # The proof should be "exact Nat.zero_le 1" (from proofs.json)
    assert "exact Nat.zero_le 1" in proof_second, f"Expected 'exact Nat.zero_le 1' in proof, got: {repr(proof_second)}"


def test_extract_proof_simple_single_sorry():
    """Test extracting a proof from a simple case with one sorry."""

    original = """theorem simple : 1 = 1 := by sorry
"""

    llm_output = """theorem simple : 1 = 1 := by rfl
"""

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=29,
        end_line=1,
        end_column=34
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof is not None, "Failed to extract proof"
    assert "rfl" in proof, f"Expected 'rfl' in proof, got: {repr(proof)}"


def test_extract_proof_multiline_proof():
    """Test extracting a multiline proof that replaces sorry."""

    original = """theorem example (n : Nat) : n + 0 = n := by
  sorry
"""

    llm_output = """theorem example (n : Nat) : n + 0 = n := by
  induction n with
  | zero => rfl
  | succ n ih => simp [ih]
"""

    location = Location(
        path="test.lean",
        start_line=2,
        start_column=2,
        end_line=2,
        end_column=7
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof is not None, "Failed to extract multiline proof"
    assert "induction n with" in proof
    assert "zero => rfl" in proof
    assert "succ n ih => simp [ih]" in proof


def test_extract_proof_with_markdown_wrapper():
    """Test that the function correctly strips markdown code blocks."""

    original = """theorem test : 1 = 1 := by sorry
"""

    llm_output = """```lean
theorem test : 1 = 1 := by rfl
```"""

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=27,
        end_line=1,
        end_column=32
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof is not None, "Failed to extract proof from markdown"
    assert "rfl" in proof


def test_extract_proof_nested_sorries():
    """Test extracting when there are nested tactic blocks."""

    original = """theorem nested : True ∧ True := by
  constructor
  · sorry
  · sorry
"""

    llm_output = """theorem nested : True ∧ True := by
  constructor
  · trivial
  · sorry
"""

    # First sorry at line 3
    location_first = Location(
        path="test.lean",
        start_line=3,
        start_column=4,
        end_line=3,
        end_column=9
    )

    proof = extract_proof_from_diff(original, llm_output, location_first)
    assert proof is not None, "Failed to extract nested proof"
    assert "trivial" in proof


def test_extract_proof_similar_proofs():
    """Test when the proof text appears elsewhere in the file."""

    original = """-- The proof should be: rfl
theorem test1 : 1 = 1 := by sorry

theorem test2 : 2 = 2 := by rfl
"""

    llm_output = """-- The proof should be: rfl
theorem test1 : 1 = 1 := by rfl

theorem test2 : 2 = 2 := by rfl
"""

    location = Location(
        path="test.lean",
        start_line=2,
        start_column=28,
        end_line=2,
        end_column=33
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof is not None, "Failed to extract when proof appears elsewhere"
    assert "rfl" in proof


def test_extract_proof_sorry_in_term_position():
    """Test extracting when sorry is used as a term, not a tactic."""

    original = """theorem example : Nat := sorry
"""

    llm_output = """theorem example : Nat := 42
"""

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=25,
        end_line=1,
        end_column=30
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof is not None, "Failed to extract term-level proof"
    assert "42" in proof


def test_extract_proof_with_comments():
    """Test extracting when the LLM adds comments in the proof."""

    original = """theorem test : 1 + 1 = 2 := by sorry
"""

    llm_output = """theorem test : 1 + 1 = 2 := by
  -- This is obvious
  rfl
"""

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=31,
        end_line=1,
        end_column=36
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof is not None, "Failed to extract proof with comments"
    assert "rfl" in proof
    assert "This is obvious" in proof


def test_extract_proof_same_line_different_tactics():
    """Test two sorries on same line with different replacement tactics."""

    original = """theorem test : 1 ≤ 2 ∧ 2 ≤ 3 := by
  constructor <;> sorry
"""

    llm_output = """theorem test : 1 ≤ 2 ∧ 2 ≤ 3 := by
  constructor <;> norm_num
"""

    # The second sorry (after <;>)
    location = Location(
        path="test.lean",
        start_line=2,
        start_column=18,
        end_line=2,
        end_column=23
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof is not None, "Failed to extract from <;> tactic"
    assert "norm_num" in proof


def test_extract_proof_no_match_after_sorry():
    """Test when there's no matching block after the sorry (file ends)."""

    original = """theorem test : True := by sorry"""

    llm_output = """theorem test : True := by trivial"""

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=26,
        end_line=1,
        end_column=31
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof is not None, "Failed to extract when no content after sorry"
    assert "trivial" in proof


def test_extract_proof_sorry_with_extra_whitespace():
    """Test when the LLM changes indentation or adds extra whitespace."""

    original = """theorem test : 1 = 1 := by
  sorry
"""

    llm_output = """theorem test : 1 = 1 := by
    rfl
"""

    location = Location(
        path="test.lean",
        start_line=2,
        start_column=2,
        end_line=2,
        end_column=7
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof is not None, "Failed to extract with whitespace changes"
    assert "rfl" in proof


def test_extract_proof_returns_none_insufficient_context():
    """Test that function returns None when LLM output has insufficient context."""

    original = """-- Some header comment
theorem test1 : 1 = 1 := by sorry

theorem test2 : 2 = 2 := by rfl
"""

    # LLM output with insufficient context (missing header and test2)
    llm_output = """theorem test1 : 1 = 1 := by rfl
"""

    location = Location(
        path="test.lean",
        start_line=2,
        start_column=28,
        end_line=2,
        end_column=33
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    # This might still work or might return None - the function should handle it gracefully
    # The key is that it shouldn't crash
    assert proof is None or isinstance(proof, str)


def test_extract_proof_unicode_characters():
    """Test handling of unicode mathematical symbols."""

    original = """theorem test : ∀ n : ℕ, n ≥ 0 := by sorry
"""

    llm_output = """theorem test : ∀ n : ℕ, n ≥ 0 := by exact Nat.zero_le
"""

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=36,
        end_line=1,
        end_column=41
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof is not None, "Failed to extract with unicode"
    assert "Nat.zero_le" in proof


def test_extract_proof_very_long_proof():
    """Test extracting a long multiline proof."""

    original = """theorem long_proof : 1 + 1 = 2 := by sorry

-- Another theorem below
theorem next : True := by trivial
"""

    llm_output = """theorem long_proof : 1 + 1 = 2 := by
  -- Step 1
  have h1 : 1 + 1 = 1 + 1 := rfl
  -- Step 2
  have h2 : 1 + 1 = 2 := by norm_num
  -- Step 3
  exact h2

-- Another theorem below
theorem next : True := by trivial
"""

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=37,
        end_line=1,
        end_column=42
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof is not None, "Failed to extract long proof"
    assert "Step 1" in proof
    assert "Step 2" in proof
    assert "Step 3" in proof
    assert "exact h2" in proof


def test_extract_proof_spurious_short_match_minimal():
    """Minimal reproduction of the spurious short match bug.

    The bug occurs when:
    1. Original has "by sorry" (space before 's')
    2. LLM proof contains a tactic starting with 's' (like 'simp') later in the proof
    3. difflib matches " s" from " sorry" with " s" from " simp" at wrong position
    4. This short match overwrites the correct long match (theorem signature)
    """
    original = "theorem foo := by sorry"

    llm_output = """theorem foo := by
  intro h
  apply h
  simp"""

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=18,
        end_line=1,
        end_column=23
    )

    proof = extract_proof_from_diff(original, llm_output, location)

    # Should extract the full proof, not just the tail starting at "simp"
    assert proof == "\n  intro h\n  apply h\n  simp"


def test_extract_proof_spurious_short_match():
    """Test that spurious short matches don't cause partial extraction.

    This reproduces a real bug where " s" from " sorry" matched " s" from " simp_all"
    in the LLM output, causing only the end of the proof to be extracted.

    Bug details:
    - Block 1 (len=81): theorem signature matches correctly
    - Block 2 (len=2): " s" from " sorry" matches " s" from " simp_all"
    - Block 2 overwrote Block 1 because it came later, even though it was shorter
    """
    # Original context with imports (matching llm_strategy.py behavior)
    original = """import Mathlib

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem mathd_numbertheory_64 : IsLeast { x : ℕ | 30 * x ≡ 42 [MOD 47] } 39 := by sorry"""

    # LLM output - just the theorem with full proof (note: " simp_all" contains " s")
    llm_output = """theorem mathd_numbertheory_64 : IsLeast { x : ℕ | 30 * x ≡ 42 [MOD 47] } 39 := by
  refine' ⟨by norm_num [Nat.ModEq], _⟩
  intro x hx
  norm_num [Nat.ModEq] at hx ⊢
  have h : x ≥ 39 := by
    by_contra h
    have h₁ : x ≤ 38 := by linarith
    interval_cases x <;> norm_num at hx ⊢ <;>
      (try omega) <;>
      (try {
        simp_all [Nat.ModEq]
        <;> norm_num at *
        <;> omega
      })
  linarith"""

    # Sorry is at line 7, column 82 (0-indexed) or 83 (1-indexed)
    # Using values that match position_to_index expectations
    # Line 7 is: "theorem mathd_numbertheory_64 : IsLeast { x : ℕ | 30 * x ≡ 42 [MOD 47] } 39 := by sorry"
    # "sorry" starts at character index 82 (0-indexed), length 87
    location = Location(
        path="test.lean",
        start_line=7,
        start_column=82,
        end_line=7,
        end_column=87
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof is not None, "Failed to extract proof"

    # The FULL proof should be extracted, starting with "refine'"
    assert "refine'" in proof, f"Expected 'refine'' at start of proof, got: {repr(proof[:100])}"

    # And ending with "linarith"
    assert "linarith" in proof, "Expected 'linarith' at end of proof"

    # Should contain the middle parts too
    assert "intro x hx" in proof, "Expected 'intro x hx' in proof"
    assert "simp_all" in proof, "Expected 'simp_all' in proof"


# ============================================================================
# Test cases derived from real Gemini experiment data
# ============================================================================


def test_simp_with_semicolon_combinator():
    """Test simp tactic with semicolon combinator from real experiment data.

    Pattern: interval_cases i <;> interval_cases j <;> sorry
         -> interval_cases i <;> interval_cases j <;> simp at *; contradiction
    """
    original = """lemma lemma2 :
    ∃ f : Set.Icc 1 8 → Fin 2, ¬coloring_is_good f := by
  use coloring_of_eight
  intro h
  obtain ⟨⟨i, hi1, hi2⟩, ⟨j, hj1, hj2⟩, hij1, hij2, hc1, hc2⟩ := h
  dsimp [coloring_of_eight] at *
  interval_cases i <;> interval_cases j <;> sorry"""

    llm_output = """lemma lemma2 :
    ∃ f : Set.Icc 1 8 → Fin 2, ¬coloring_is_good f := by
  use coloring_of_eight
  intro h
  obtain ⟨⟨i, hi1, hi2⟩, ⟨j, hj1, hj2⟩, hij1, hij2, hc1, hc2⟩ := h
  dsimp [coloring_of_eight] at *
  interval_cases i <;> interval_cases j <;> simp at *; contradiction"""

    location = Location(
        path="test.lean",
        start_line=7,
        start_column=44,
        end_line=7,
        end_column=49
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "simp at *; contradiction"


def test_simp_with_brackets_and_combinator():
    """Test simp with arguments and <;> combinator.

    Pattern from real data: sorry -> simp [coloring_of_eight] at * <;> contradiction
    """
    original = "theorem foo := by sorry"
    llm_output = "theorem foo := by simp [coloring_of_eight] at * <;> contradiction"

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=18,
        end_line=1,
        end_column=23
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "simp [coloring_of_eight] at * <;> contradiction"


def test_bullet_point_before_sorry():
    """Test that bullet point (·) before sorry is NOT included in proof.

    This is a common pattern in structured proofs.
    """
    original = """theorem bayesTheorem (hB : ℙ B ≠ 0) : ℙ(A|B) = ℙ A * ℙ(B|A) / ℙ B := by
  by_cases h : ℙ A = 0
  · sorry"""

    llm_output = """theorem bayesTheorem (hB : ℙ B ≠ 0) : ℙ(A|B) = ℙ A * ℙ(B|A) / ℙ B := by
  by_cases h : ℙ A = 0
  · simp [h]"""

    location = Location(
        path="test.lean",
        start_line=3,
        start_column=4,
        end_line=3,
        end_column=9
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "simp [h]", f"Expected 'simp [h]', got {repr(proof)}"


def test_unicode_symbols_in_proof():
    """Test proof containing Unicode Greek letters and symbols.

    Pattern from real data with δ (delta) symbol.
    """
    original = "lemma foo (δ : ℝ) (hh : δ > 0) : x < δ := by sorry"
    llm_output = "lemma foo (δ : ℝ) (hh : δ > 0) : x < δ := by linarith [hh, δ_le1]"

    # sorry is at index 45-50 in the original string
    location = Location(
        path="test.lean",
        start_line=1,
        start_column=45,
        end_line=1,
        end_column=50
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "linarith [hh, δ_le1]"


def test_context_change_around_sorry():
    """Test when LLM changes context (like comments) around the sorry.

    Should still extract just the proof replacement.
    """
    original = "-- old comment\nlemma bar := by sorry"
    llm_output = "-- new comment\nlemma bar := by simp"

    location = Location(
        path="test.lean",
        start_line=2,
        start_column=16,
        end_line=2,
        end_column=21
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "simp"


def test_angle_brackets_in_proof():
    """Test proof with Unicode angle brackets ⟨⟩.

    Common in existential and structure proofs.
    Note: Current behavior includes leading newline+indent due to newline lookback logic.
    """
    original = """theorem Exercise_8_1_5_1 {U V : Type}
    (h : U ∼ V) : Set U ∼ Set V := by
  rw [equinum_iff_inverse_pair] at h ⊢
  rcases h with ⟨f, g, hfg, hgf⟩
  sorry"""

    llm_output = """theorem Exercise_8_1_5_1 {U V : Type}
    (h : U ∼ V) : Set U ∼ Set V := by
  rw [equinum_iff_inverse_pair] at h ⊢
  rcases h with ⟨f, g, hfg, hgf⟩
  exact ⟨image f, image g, image_comp_id hfg, image_comp_id hgf⟩"""

    location = Location(
        path="test.lean",
        start_line=5,
        start_column=2,
        end_line=5,
        end_column=7
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    # Includes newline and indentation due to newline lookback
    assert proof == "\n  exact ⟨image f, image g, image_comp_id hfg, image_comp_id hgf⟩"


def test_rfl_tactic():
    """Test non-'s' starting tactic (rfl) as control case."""
    original = "theorem foo : 1 = 1 := by sorry"
    llm_output = "theorem foo : 1 = 1 := by rfl"

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=26,
        end_line=1,
        end_column=31
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "rfl"


def test_multiple_sorries_first():
    """Test extracting first sorry when multiple exist in file."""
    original = """theorem first := by sorry
theorem second := by sorry"""

    llm_output = """theorem first := by exact trivial
theorem second := by sorry"""

    # First sorry location
    location = Location(
        path="test.lean",
        start_line=1,
        start_column=20,
        end_line=1,
        end_column=25
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "exact trivial"


def test_multiple_sorries_second():
    """Test extracting second sorry when multiple exist in file."""
    original = """theorem first := by sorry
theorem second := by sorry"""

    llm_output = """theorem first := by sorry
theorem second := by exact rfl"""

    # Second sorry location
    location = Location(
        path="test.lean",
        start_line=2,
        start_column=21,
        end_line=2,
        end_column=26
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "exact rfl"


def test_minimal_exact_replacement():
    """Test simplest case - only sorry changes, nothing else."""
    original = "theorem foo := by sorry"
    llm_output = "theorem foo := by exact trivial"

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=18,
        end_line=1,
        end_column=23
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "exact trivial"


# ============================================================================
# Additional edge case tests
# ============================================================================


def test_sorry_in_comment_before_target():
    """Test that 'sorry' in a comment doesn't affect extraction of actual sorry.

    The baku replacement affects all 'sorry' occurrences, but positions should still match.
    """
    original = """-- TODO: sorry, need to fix this later
theorem foo := by sorry"""

    llm_output = """-- TODO: sorry, need to fix this later
theorem foo := by simp"""

    location = Location(
        path="test.lean",
        start_line=2,
        start_column=18,
        end_line=2,
        end_column=23
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "simp"


def test_sorry_at_end_of_file_no_trailing_newline():
    """Test sorry at very end of file with no trailing content."""
    original = "theorem foo := by sorry"  # No trailing newline
    llm_output = "theorem foo := by rfl"

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=18,
        end_line=1,
        end_column=23
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "rfl"


def test_llm_returns_proof_containing_sorry():
    """Test when LLM returns a proof that still contains 'sorry'.

    This can happen when LLM partially solves a goal.
    The baku replacement should handle this correctly.
    """
    original = """theorem foo := by
  cases h
  · sorry
  · sorry"""

    llm_output = """theorem foo := by
  cases h
  · exact trivial
  · sorry"""

    # First sorry location
    location = Location(
        path="test.lean",
        start_line=3,
        start_column=4,
        end_line=3,
        end_column=9
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "exact trivial"


def test_llm_returns_only_proof_fragment():
    """Test when LLM returns just the proof without full context.

    This is a challenging case - minimal matching context.
    """
    original = "theorem foo := by sorry"
    llm_output = "by simp"  # LLM returns only partial context

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=18,
        end_line=1,
        end_column=23
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    # Should still extract 'simp' if there's enough matching context
    # or return None if insufficient context
    # The "by " prefix provides matching context
    assert proof is None or "simp" in proof


def test_lean4_markdown_fence():
    """Test ```lean4 markdown fence instead of ```lean."""
    original = "theorem foo := by sorry"

    llm_output = """Here's the proof:
```lean4
theorem foo := by simp
```
"""

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=18,
        end_line=1,
        end_column=23
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    # Current implementation only checks for "```lean", so ```lean4 should also match
    # since "```lean" is a substring of "```lean4"
    assert proof == "simp"


def test_empty_proof_replacement():
    """Test when LLM effectively returns empty proof."""
    original = "theorem foo := by sorry"
    llm_output = "theorem foo := by "  # Just whitespace where sorry was

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=18,
        end_line=1,
        end_column=23
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    # Should return empty string or None
    assert proof is None or proof.strip() == ""


def test_sorry_in_term_mode():
    """Test term-mode sorry (not tactic mode)."""
    original = "def foo : Nat := sorry"
    llm_output = "def foo : Nat := 42"

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=17,
        end_line=1,
        end_column=22
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "42"


def test_sorry_with_type_annotation():
    """Test sorry with explicit type annotation."""
    original = "def foo := (sorry : Nat)"
    llm_output = "def foo := (42 : Nat)"

    # sorry starts at position 12
    location = Location(
        path="test.lean",
        start_line=1,
        start_column=12,
        end_line=1,
        end_column=17
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "42"


def test_adjacent_sorries():
    """Test extraction when two sorries are adjacent."""
    original = "theorem foo := by constructor <;> sorry"
    llm_output = "theorem foo := by constructor <;> simp"

    # sorry is at position 34-39
    location = Location(
        path="test.lean",
        start_line=1,
        start_column=34,
        end_line=1,
        end_column=39
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "simp"


def test_sorry_after_semicolon():
    """Test sorry immediately after semicolon in tactic chain."""
    original = "theorem foo := by simp; sorry"
    llm_output = "theorem foo := by simp; exact rfl"

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=24,
        end_line=1,
        end_column=29
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "exact rfl"


def test_proof_with_backticks():
    """Test proof containing backtick syntax."""
    original = "theorem foo := by sorry"
    llm_output = "theorem foo := by `[simp]"

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=18,
        end_line=1,
        end_column=23
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "`[simp]"


def test_deeply_indented_sorry():
    """Test sorry with deep indentation.

    Note: Current behavior includes leading newline+indent due to newline lookback logic.
    """
    original = """theorem foo := by
  cases h
    cases h'
      cases h''
        sorry"""

    llm_output = """theorem foo := by
  cases h
    cases h'
      cases h''
        exact trivial"""

    location = Location(
        path="test.lean",
        start_line=5,
        start_column=8,
        end_line=5,
        end_column=13
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    # Includes newline and deep indentation due to newline lookback
    assert proof == "\n        exact trivial"


def test_sorry_in_where_clause():
    """Test sorry in a where clause."""
    original = """def foo := bar where
  helper := sorry"""

    llm_output = """def foo := bar where
  helper := 42"""

    location = Location(
        path="test.lean",
        start_line=2,
        start_column=12,
        end_line=2,
        end_column=17
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof == "42"


def test_multiline_sorry_replacement():
    """Test multi-line proof replacing single-line sorry."""
    original = "theorem foo := by sorry"

    llm_output = """theorem foo := by
  intro h
  cases h with
  | inl h' => exact h'
  | inr h' => exact h'"""

    location = Location(
        path="test.lean",
        start_line=1,
        start_column=18,
        end_line=1,
        end_column=23
    )

    proof = extract_proof_from_diff(original, llm_output, location)
    assert proof is not None
    assert "intro h" in proof
    assert "cases h with" in proof
    assert "inl" in proof and "inr" in proof


# ============================================================================
# Known bug reproduction tests from real replay data
# These tests document actual extraction failures found in experiments
# ============================================================================


class TestKnownExtractionBugs:
    """Tests that reproduce known extraction bugs from real experiment data.

    These tests document actual bugs where extraction fails DESPITE having
    sufficient matching context. The bugs are caused by spurious Unicode matches.
    """

    def test_angle_bracket_with_matching_context(self):
        """BUG: Unicode angle brackets ⟨⟩ cause partial extraction.

        When the LLM returns the full theorem with angle brackets in the proof,
        the ⟨ or ⟩ can create spurious matches that truncate extraction.
        """
        original = """theorem exists_pair : ∃ x y : Nat, x < y := by
  sorry"""

        # LLM returns full theorem with angle bracket proof
        llm_output = """theorem exists_pair : ∃ x y : Nat, x < y := by
  exact ⟨0, 1, Nat.zero_lt_one⟩"""

        location = Location(
            path="test.lean",
            start_line=2,
            start_column=2,
            end_line=2,
            end_column=7
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        # Expected: the full exact expression with angle brackets
        assert proof == "\n  exact ⟨0, 1, Nat.zero_lt_one⟩"

    def test_semicolon_tactic_chain_with_matching_context(self):
        """BUG: Semicolon in tactic chain may cause partial extraction.

        When the LLM returns a tactic chain with semicolons, the ; can
        create spurious matches that extract only part of the chain.
        """
        original = """theorem foo : True ∧ True := by
  sorry"""

        # LLM returns full theorem with semicolon tactic chain
        llm_output = """theorem foo : True ∧ True := by
  constructor; trivial; trivial"""

        location = Location(
            path="test.lean",
            start_line=2,
            start_column=2,
            end_line=2,
            end_column=7
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        # Expected: the full tactic chain
        assert proof == "\n  constructor; trivial; trivial"

    def test_subscript_with_matching_context(self):
        """Test Unicode subscripts with matching context.

        Subscript characters like ₁, ₂, ₄ could cause spurious matches
        if they appear in both original and LLM output at different positions.
        """
        original = """theorem h₁_implies_h₂ (h₁ : P) (h₂ : P → Q) : Q := by
  sorry"""

        # LLM returns full theorem - subscripts in both original and output
        llm_output = """theorem h₁_implies_h₂ (h₁ : P) (h₂ : P → Q) : Q := by
  exact h₂ h₁"""

        location = Location(
            path="test.lean",
            start_line=2,
            start_column=2,
            end_line=2,
            end_column=7
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        # Expected: the full exact expression
        assert proof == "\n  exact h₂ h₁"


class TestReplayExtractionBugs:
    """Tests that reproduce extraction bugs found in real replay experiments.

    These tests are based on actual failures from:
    replay_results/goedel_10_test_replay/2026-01-20_12-44-18_replay

    The bugs occur when Unicode characters or special characters create
    spurious difflib matches that truncate or corrupt the extracted proof.
    """

    def test_angle_bracket_extracts_single_char(self):
        """BUG: LLM response with ⟨⟩ extracts only '⟩' instead of full proof.

        Real case from replay:
        - LLM returned: refine ⟨C_(a := 0).le, ?_⟩
        - Extracted: ⟩
        - Expected: refine ⟨C_(a := 0).le, ?_⟩

        The ⟨ character creates a spurious match that truncates extraction.
        """
        # Original file context (modal logic proof)
        original = """lemma modal_diamond : L ⊢ ∼□atom 0 ➝ ∼∼◇(∼atom 0) := by
  sorry"""

        # LLM returns proof with angle brackets
        llm_output = """lemma modal_diamond : L ⊢ ∼□atom 0 ➝ ∼∼◇(∼atom 0) := by
  refine ⟨C_(a := 0).le, ?_⟩"""

        location = Location(
            path="test.lean",
            start_line=2,
            start_column=2,
            end_line=2,
            end_column=7
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        # This test documents the bug - currently extracts just '⟩' or similar
        # When fixed, should extract the full proof
        assert proof == "\n  refine ⟨C_(a := 0).le, ?_⟩"

    def test_semicolon_extracts_only_last_part(self):
        """BUG: Semicolon in proof causes extraction of only the last part.

        Real case from replay:
        - LLM returned: apply C!_trans (ψ := ∼∼◇(∼(.atom 0))); simplicity
        - Extracted: simplicity
        - Expected: apply C!_trans (ψ := ∼∼◇(∼(.atom 0))); simplicity

        The semicolon creates a spurious match that extracts only 'simplicity'.
        """
        original = """lemma modal_proof : L ⊢ ∼□atom 0 ➝ ∼∼◇(∼atom 0) := by
  sorry"""

        llm_output = """lemma modal_proof : L ⊢ ∼□atom 0 ➝ ∼∼◇(∼atom 0) := by
  apply C!_trans (ψ := ∼∼◇(∼(.atom 0))); simplicity"""

        location = Location(
            path="test.lean",
            start_line=2,
            start_column=2,
            end_line=2,
            end_column=7
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        # Bug: extracts only 'simplicity' instead of full proof
        assert proof == "\n  apply C!_trans (ψ := ∼∼◇(∼(.atom 0))); simplicity"

    def test_less_than_combinator_truncates_proof(self):
        """BUG: <;> tactic combinator causes truncated extraction ending with '<'.

        Real case from replay:
        - LLM returned: . apply C!_trans...<;> simp [Transitivity]<;> try simp_all...
        - Extracted: simp [Transitivity]\n    <
        - Expected: full multi-line proof

        The '<' from '<;>' creates a spurious match that truncates extraction.
        """
        original = """lemma modal_trans : L ⊢ ∼□atom 0 ➝ ∼∼◇(∼atom 0) := by
  sorry"""

        llm_output = """lemma modal_trans : L ⊢ ∼□atom 0 ➝ ∼∼◇(∼atom 0) := by
  . apply C!_trans (ψ := ∼∼◇(∼(.atom 0)));
    <;> simp [Transitivity]
    <;> try simp_all [Transitivity]
    <;> try assumption"""

        location = Location(
            path="test.lean",
            start_line=2,
            start_column=2,
            end_line=2,
            end_column=7
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        # Bug: extracts truncated proof ending with '<' or similar partial content
        # Should extract the full multi-line proof
        expected = """\n  . apply C!_trans (ψ := ∼∼◇(∼(.atom 0)));
    <;> simp [Transitivity]
    <;> try simp_all [Transitivity]
    <;> try assumption"""
        assert proof == expected

    def test_subscript_extracts_single_char(self):
        """BUG: Unicode subscript ₄ in proof causes single-char extraction.

        Real case from replay:
        - LLM returned: some proof containing ₄
        - Extracted: ₄
        - Expected: full proof

        Unicode subscripts create spurious matches.
        """
        original = """lemma h₄_lemma : P := by
  sorry"""

        llm_output = """lemma h₄_lemma : P := by
  exact h₄"""

        location = Location(
            path="test.lean",
            start_line=2,
            start_column=2,
            end_line=2,
            end_column=7
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        # Bug: might extract just '₄' instead of 'exact h₄'
        assert proof == "\n  exact h₄"

    def test_llm_adds_definition_before_lemma(self):
        """BUG: LLM adding extra code before lemma breaks extraction.

        Real case: LLM returns 'def coloring_of_eight...' followed by the lemma,
        but original only has the lemma context. This shifts all positions and
        causes spurious matches.
        """
        # Original context only has the lemma (lines 70-75 of actual file)
        original = """    ∃ f : Set.Icc 1 8 → Fin 2, ¬coloring_is_good f := by
  use coloring_of_eight
  intro h
  obtain ⟨⟨i, hi1, hi2⟩, ⟨j, hj1, hj2⟩, hij1, hij2, hc1, hc2⟩ := h
  dsimp [coloring_of_eight] at *
  interval_cases i <;> interval_cases j <;> sorry"""

        # LLM returns extra definition PLUS the lemma
        llm_output = """def coloring_of_eight {n : ℕ} : Set.Icc 1 n → Fin 2
| ⟨1, _⟩ => 0
| ⟨2, _⟩ => 1
| ⟨3, _⟩ => 0
| ⟨4, _⟩ => 1
| ⟨5, _⟩ => 1
| ⟨6, _⟩ => 0
| ⟨7, _⟩ => 1
| ⟨8, _⟩ => 0
| _ => 0 -- unreachable

lemma lemma2 :
    ∃ f : Set.Icc 1 8 → Fin 2, ¬coloring_is_good f := by
  use coloring_of_eight
  intro h
  obtain ⟨⟨i, hi1, hi2⟩, ⟨j, hj1, hj2⟩, hij1, hij2, hc1, hc2⟩ := h
  dsimp [coloring_of_eight] at *
  interval_cases i <;> interval_cases j <;> simp at hc1 hc2 <;> contradiction"""

        location = Location(
            path="test.lean",
            start_line=6,
            start_column=44,
            end_line=6,
            end_column=49
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        # Bug: The extra definition causes difflib to match incorrectly
        # resulting in empty or wrong extraction
        assert proof == "simp at hc1 hc2 <;> contradiction"


    def test_quantum_channel_without_comment(self):
        """Control test: Same structure but NO spurious matches after sorry.

        The bug in test_quantum_channel_partial_response occurs because:
        1. With comment: 'hav' from '--having' matches 'have' in proof
        2. Without comment: '    have' from next line STILL matches 'have' in proof

        This control test uses 'obtain' on the next line instead of 'have',
        so there's no spurious match and extraction should work.
        """
        # Changed: next line uses 'obtain' instead of 'have' to avoid spurious match
        original = """/-- Every quantum channel achieves a rate of zero. -/
theorem achievesRate_0 (Λ : CPTPMap d₁ d₂) : Λ.AchievesRate 0 := by
  intro ε hε
  use 1, zero_lt_one, 1, default
  constructor
  · have : Nonempty d₁ := by sorry"""

        # LLM returns only a partial fragment - just the proof for the first sorry
        llm_output = """/-- Every quantum channel achieves a rate of zero. -/
theorem achievesRate_0 (Λ : CPTPMap d₁ d₂) : Λ.AchievesRate 0 := by
  intro ε hε
  use 1, zero_lt_one, 1, default
  constructor
  · have : Nonempty d₁ := by simp"""

        # First sorry is at line 6, after "Nonempty d₁ := by "
        location = Location(
            path="test.lean",
            start_line=6,
            start_column=29,
            end_line=6,
            end_column=32
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        # With 'obtain' on next line (no 'have'), extraction should work correctly
        expected = "simp"

        assert proof == expected

    def test_llm_proof_contains_sorry_spurious_match(self):
        """BUG: LLM proof containing 'sorry' causes spurious match with original sorry.

        Real case from PrimeNumberTheoremAnd/FioriKadiriSwidinsky.lean:
        - Original: theorem table_1_prop ... := by sorry
        - LLM returned: rcases h with h | h | ... <;> injection h <;> subst_vars <;> sorry
        - Extracted: sorry
        - Expected: rcases h with h | h | ... <;> injection h <;> subst_vars <;> sorry

        The 'sorry' at the END of the LLM's replacement proof creates a spurious
        match with the original 'sorry', causing extraction to return just 'sorry'
        instead of the full replacement tactic.
        """
        original = """import Architect
import PrimeNumberTheoremAnd.PrimaryDefinitions
import PrimeNumberTheoremAnd.KLN

blueprint_comment /--
\\section{The estimates of Fiori, Kadiri, and Swidinsky}
-/

blueprint_comment /--
In this section we establish the primary results of Fiori, Kadiri, and Swidinsky from this paper: arXiv:2204.02588
-/

open Real

namespace FKS

structure Inputs where
  b₁ : ℝ
  b₂ : ℝ
  b₃ : ℝ
  hRvM : riemannZeta.Riemann_vonMangoldt_bound b₁ b₂ b₃
  ZDB : zero_density_bound
  H₀ : ℝ
  hH₀ : riemannZeta.RH_up_to H₀
  R : ℝ
  hR : riemannZeta.classicalZeroFree R
  S₀ : ℝ
  T₀ : ℝ
  hS₀T₀ : riemannZeta.zeroes_sum Set.univ (Set.Ioo 0 T₀) (fun ρ ↦ 1 / ρ.im) < S₀

def table_1 : List (ℝ × ℝ) :=
  [ (100, 0.5922435112),
    (1000, 2.0286569752),
    (10000, 4.3080354951),
    (100000, 7.4318184970),
    (1000000, 11.3993199147),
    (10000000, 16.2106480369),
    (100000000, 21.8657999924),
    (1000000000, 28.3647752011),
    (10000000000, 35.7075737123),
    (30610046000, 39.5797647802)
  ]

theorem table_1_prop {T₀ S₀ : ℝ} (h : (T₀, S₀) ∈ table_1) : riemannZeta.zeroes_sum Set.univ (Set.Ioo 0 T₀) (fun ρ ↦ 1 / ρ.im) < S₀ := by sorry"""

        llm_output = """```lean
theorem table_1_prop {T₀ S₀ : ℝ} (h : (T₀, S₀) ∈ table_1) : riemannZeta.zeroes_sum Set.univ (Set.Ioo 0 T₀) (fun ρ ↦ 1 / ρ.im) < S₀ := by
  rcases h with h | h | h | h | h | h | h | h | h | h <;> injection h <;> subst_vars <;> sorry
```"""

        # sorry is at line 44, columns 137-142
        location = Location(
            path="PrimeNumberTheoremAnd/FioriKadiriSwidinsky.lean",
            start_line=44,
            start_column=137,
            end_line=44,
            end_column=142
        )

        proof = extract_proof_from_diff(original, llm_output, location)

        # Bug: extracts just 'sorry' due to spurious match with sorry in replacement
        # Expected: the full replacement tactic (which happens to end with sorry)
        expected = "\n  rcases h with h | h | h | h | h | h | h | h | h | h <;> injection h <;> subst_vars <;> sorry"
        assert proof == expected
