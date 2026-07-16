import Mathlib

namespace Triangular

/-- `T n = 1 + 2 + ... + n`. -/
def T (n : Nat) : Nat := Finset.sum (Finset.range (n + 1)) id

/-- A natural number is triangular if it equals `T n` for some `n`. -/
def IsTriangular (m : Nat) : Prop := ∃ n, m = T n

/-- The closed form `2 * T n = n * (n + 1)`, no `sorry` — unlike the gauss
example, this one is fully checked, to show a `lean_ok` (not `sorry`) leaf. -/
theorem closed_form (n : Nat) : 2 * T n = n * (n + 1) := by
  induction n with
  | zero => rfl
  | succ k ih => simp [T, Finset.sum_range_succ, Nat.mul_add, ih]; ring

/-- Decidability instance for `IsTriangular` — a Lean-only node (no matching
blueprint `\lean{}`), demonstrating `content_type: instance`. -/
instance decidableIsTriangular (m : Nat) : Decidable (IsTriangular m) :=
  decidable_of_iff (m = T m ∨ ∃ n ≤ m, m = T n) (by sorry)

end Triangular
