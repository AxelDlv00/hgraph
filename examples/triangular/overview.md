# About this example

Triangular numbers ($T_n = 1 + 2 + \cdots + n$), synced from a small blueprint
+ Lean pair. Where [gauss](../gauss/) shows the *sync* workflow end to end,
this one is built to exercise the rest of the schema.

- Every `content_type` gauss doesn't: `proposition`, `corollary`, `example`, `remark`, `conjecture`, and a Lean-only `instance`.
- A wider spread of `origin` values, a `lang` tag, and `status: false`/`built`.
- A **stale-node demo**: `build.sh` syncs once with an extra labeled statement, then again without it, so you can watch `stale: true` appear.
- The new two-axis review shape — Maths good/bad and Lean good/bad, independently.
- A `related_to` edge on a hand-added node.

See the [source and build script](https://github.com/AxelDlv00/hgraph/tree/main/examples/triangular).
