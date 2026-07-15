# Example — Gauss summation (synced from a blueprint)

The blueprint (`blueprint/blueprint.tex`) and the Lean sources (`Lean/*.lean`)
are the **reference**. `hgraph sync` parses them into the graph; a human/agent
then layers on what those files can't hold. Run:

```bash
bash examples/gauss/build.sh
```

## The sources

`blueprint/blueprint.tex` uses the leanblueprint conventions:

```latex
\begin{lemma}[Sum of evens]\label{lem:even-add}\lean{Gauss.isEven_add}\uses{def:even}\leanok
If $a$ and $b$ are even then $a + b$ is even.
\end{lemma}
```

- `\label{…}` — the item's **identity**. Blueprint nodes are keyed on it.
- `\lean{…}` — the Lean declaration(s) it corresponds to → a `formalizes` edge.
- `\uses{…}` — dependencies (labels). In a **statement** → `depends_on`; inside a
  `\begin{proof}` → `uses`.

`Lean/Basic.lean` + `Lean/Gauss.lean` hold the declarations. Each becomes a Lean
node keyed on its **fully-qualified name** (`Gauss.isEven_add`), carrying its
`file`, `docstring`, and `lean_status` (`sorry` if the source still has a
`sorry`, else `lean_ok`). A tex node's `lean_status` is **aggregated** from the
Lean node(s) it formalizes (recomputed each sync, so the two can't disagree);
`\mathlibok` marks it `mathlib_ok` and records the `mathlib_name`. Every node
also gets `author` / `created` / `updated`.

## Two independent node populations

There is no 1-to-1 correspondence — `\lean{…}` is a *many-to-many* link:

| population | keyed on | id | example |
|---|---|---|---|
| blueprint | LaTeX `\label` | `sha1("bp:"+label)[:12]` | `lem:even-add` |
| Lean | fully-qualified name | `sha1("lean:"+fqname)[:12]` | `Gauss.isEven_add` |

`Gauss.isEven_zero` exists in `Basic.lean` with no blueprint entry — it becomes a
Lean node with no incoming `formalizes`, and the graph tracks it anyway.

Ids are opaque and uniform — and so are hand-added nodes, which hash a `--key`
(default: the title). You never type a hash; reference a node by its key:

```bash
hgraph get label:thm:gauss             # blueprint node, by \label
hgraph get decl:Gauss.isEven_mul_succ  # Lean node, by fq-name
hgraph get key:even-quote              # hand-added node, by --key
```

## Owned vs authored — why a re-sync is safe

`sync` writes **only the fields it owns** (title, content_type, body,
`lean_status`, and a Lean node's `file`/`docstring`) and the edges it generated
(tagged `generated:`). Step 2 of the build adds everything the `.tex` cannot
express:

- structured `origin` + `origin_details` on the theorem (provenance);
- authored `status` (`draft` / `verified` / `failed`) and `tags` on several nodes;
- a source-quote node (`--author human`, `--key even-quote`) + an associative
  `quote` edge;
- two **comments** (a debugging progression, each with a `--title`) on the still-
  `sorry` lemma, stored as attachments under `nodes/<id>/comment-N.md`;
- two **reviews** carrying a `--verdict` (`good` / `bad`), a `--quality` rating,
  a `--title` and `--confidence` — one on the lemma (`bad`, unfinished proof),
  one on the theorem (`good`).

Every node also carries auto `author` / `created` / `updated`. Step 3 runs `sync`
**again**: bodies are re-derived, but all of the above survives untouched, and
because `updated` only bumps on a real change, unchanged files aren't even
rewritten. A `\label` that disappears isn't deleted — it's flagged `stale: true`,
so its comments and metadata are never lost.

The blueprint also carries a Mathlib-backed lemma (`\label{lem:sum-succ}` with
`\mathlibok` and `\lean{Finset.sum_range_succ}`): it gets `lean_status:
mathlib_ok` and `mathlib_name: [Finset.sum_range_succ]`, with no local Lean node.

## What the views show

- **`hgraph get decl:Gauss.isEven_mul_succ`** — the re-derived Lean body,
  `lean_status: sorry`, the `formalizes` link back to the blueprint lemma, and
  the preserved comments and review.
- **`hgraph ancestors label:thm:gauss --names`** — the transitive dependencies
  pulled from `\uses`.
- **`hgraph view union`** — each blueprint item and its Lean declaration merge
  into **one** conceptual node (they're joined by `formalizes`, an *identity*
  link), while the source quote and the blueprint-less `Gauss.isEven_zero` stay
  separate. `--dot` emits Graphviz.

## Edge classes

Edge files are named `<src>__<tgt>.md` (one per ordered pair); the type is in
the YAML. When a statement and a proof both `\uses` the same target, the two
collapse to the stronger `depends_on`.

| class | types here | source | merges in union view? |
|-------|-----------|--------|:---:|
| hard | `depends_on` (statement `\uses`), `uses` (proof `\uses`) | generated | no |
| identity (soft) | `formalizes` (`\lean`) | generated | **yes** |
| associative (soft) | `quote` | authored | no |

(Comments aren't edges — they're attachments under `nodes/<id>/`.)
