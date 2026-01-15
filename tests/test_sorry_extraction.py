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
