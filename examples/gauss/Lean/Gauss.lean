import Mathlib
import Gauss.Basic

namespace Gauss

/-- Gauss's summation formula, in the division-free form
`2 * (0 + 1 + ... + n) = n * (n + 1)`. -/
theorem sum_range_id (n : Nat) :
    2 * (∑ i ∈ Finset.range (n + 1), i) = n * (n + 1) := by
  sorry

def sum_range_id' (n : Nat) : 2 * (∑ i in Finset.range (n + 1), i) = n * (n + 1) :=
  sum_range_id n

end Gauss
