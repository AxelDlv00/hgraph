import Mathlib

namespace Gauss

/-- A natural number is even if it is twice some `k`. -/
def IsEven (n : Nat) : Prop := ∃ k, n = 2 * k

/-- Zero is even. -/
theorem isEven_zero : IsEven 0 := ⟨0, rfl⟩

/-- The sum of two even numbers is even. -/
theorem isEven_add {a b : Nat} (ha : IsEven a) (hb : IsEven b) :
    IsEven (a + b) := by
  obtain ⟨i, rfl⟩ := ha
  obtain ⟨j, rfl⟩ := hb
  exact ⟨i + j, by ring⟩

/-- For every `n`, the product `n * (n + 1)` is even. -/
theorem isEven_mul_succ (n : Nat) : IsEven (n * (n + 1)) := by
  sorry

end Gauss
