---
author: sync
content_type: definition
created: '2026-07-16T16:39:36'
decl: Triangular.T
docstring: '`T n = 1 + 2 + ... + n`.'
file: Lean/Triangular.lean
generated: lean
lean_status: lean_ok
title: Triangular.T
type: lean
updated: '2026-07-16T16:39:36'
---
def T (n : Nat) : Nat := Finset.sum (Finset.range (n + 1)) id