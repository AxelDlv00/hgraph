# Example — Triangular numbers (the rest of the schema)

[gauss](../gauss/) walks through the `sync` workflow end to end. This example
is a second, equally small blueprint + Lean pair, built instead to exercise
the schema fields gauss doesn't touch. Run:

```bash
bash examples/triangular/build.sh
```

## What it adds over gauss

- **`content_type` diversity.** Gauss only needs `definition`/`lemma`/
  `theorem`. This one's blueprint uses `proposition`, `corollary`, `example`,
  `remark`, and `conjecture` (the last one explicitly caveated in its own
  text — it's a real theorem, kept as `conjecture` only to demonstrate the
  field); its Lean side adds a Lean-only `instance` node (`content_type:
  instance`, no matching blueprint `\lean{}`).
- **A wider `origin` spread** — `textbook` (with `origin_details`),
  `lecture-notes`, `article`, `preprint`, `ai`, `repository`, `unknown` — plus
  a `lang: en` tag.
- **`status: false` / `status: built`**, the two values gauss's `draft` /
  `verified` / `failed` don't cover.
- **A stale-node demo.** `build.sh` syncs once against a blueprint copy with
  one extra labeled statement (`lem:scratch-demo`), then again against the
  real committed blueprint (without it) — watch it flip to `stale: true`
  instead of disappearing.
- **Two hand-added nodes**: a `content_type: quote` source quote, and a
  `content_type: proof` alternative proof linked to the theorem it re-proves
  by a `related_to` edge (associative — the theorem doesn't depend on it).
- **The two-axis review shape** — a Maths good/bad *and* Lean good/bad
  review on the theorem, and a single-axis (Maths-only) review on the
  corollary.
- **`hgraph site`**, run with no `--manifest` — it reads the `site:` block in
  `hgraph/config.yaml` and synthesizes a one-project `index.html` +
  `data.json`, the same as a multi-project workspace would.

## Layout

| Path | What it is |
|------|-----------|
| `blueprint/blueprint.tex` | the whole blueprint (flat, no `\input`) |
| `Lean/Triangular.lean` | `T`, `IsTriangular`, `closed_form` (no `sorry`), and the `instance` |
| `hgraph/config.yaml` | `blueprint`/`lean` paths + the `site:` block |
| `overview.md` | the landing page's hero blurb, in Markdown |
| `build.sh` | sync → layer on metadata → stale demo → the site |

## Note on committed files

Only the sources are committed (`blueprint/`, `Lean/`, `hgraph/config.yaml`,
`overview.md`, `build.sh`, this README). The generated graph
(`hgraph/nodes`, `hgraph/edges`) and the built `index.html`/`assets/`/
`data.json` are git-ignored; run `build.sh` to regenerate them.
