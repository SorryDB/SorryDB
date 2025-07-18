import Lean

theorem test : 1 + 1 = 2 := by
  have someLemma : True := by
    sorry
  sorry


theorem test' : 1 + 1 = 2 :=
  sorry


theorem test'' : ∃ a : Nat, a + 2 = 3 ∧ a = 1 := by
  refine ⟨?a, ?b, ?c⟩
  case b =>
    --This goal contains a metavariable
    sorry
  case c => exact rfl


theorem test''' : ∃ a : Nat, a + 2 = 3 ∧ a = 1 := by
  refine ⟨?a, ?b, ?c⟩
  case c => exact rfl
  case b =>
    -- no metavariable!
    sorry
