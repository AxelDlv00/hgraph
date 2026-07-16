# Two examples 

These two examples are minimal, it is just to show how to use `hgraph` to build a site from Lean sources.

Both projects below are built the same way: a `leanblueprint`-style `.tex` +
Lean sources, parsed by `hgraph sync` into a plain-files graph. This whole
site — this landing page and each project's statements — is `hgraph site`.

- **Sync workflow** shows the end-to-end pipeline: sync, layer on provenance/comments/reviews by hand, re-sync (idempotent).
- **Schema reference** exercises the rest of the schema — every `content_type`, a wide `origin` spread, a stale-node demo, and the Maths/Lean review shape.

See the [source, docs, and CLI](https://github.com/AxelDlv00/hgraph).
