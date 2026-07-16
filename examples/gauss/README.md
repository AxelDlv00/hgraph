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
- `\uses{…}` — dependencies (labels), in a **statement** or inside a
  `\begin{proof}` alike → a `uses` edge (the one hard edge type).

## Chapters and bibliography

The blueprint is a `report`, split by `\chapter` into **Parity** (the parity
groundwork) and **The summation formula** (the Mathlib-backed splitting lemma
and the theorem). Only `\chapter` starts a chapter; `\section` and below stay
inside one as ordinary headings. Chapters are not decoration — they drive:

- the document view's chapter-by-chapter reading order and its outline;
- each statement's `chapter` field (`hgraph get label:thm:gauss`), which the
  graph also falls back on when grouping nodes that have no dependencies;
- **chapter-scoped numbering** — `Def 1.1`, `Lem 1.3`, then `Thm 2.2`;
- the Summary tab's per-chapter coverage table (Parity 67%, summation 50%).

`blueprint/refs.bib` is picked up because it sits under the blueprint's
directory — any `.bib` there is parsed, deduped by key. A `\cite{…}` in a
statement body renders as a link into the **Bibliography** tab, which lists each
entry with the statements citing it:

| entry | cited from |
|---|---|
| Sartorius von Waltershausen (1856), the schoolboy anecdote | `thm:gauss` |
| Graham, Knuth & Patashnik, *Concrete Mathematics* | `lem:mul-succ`, `thm:gauss` |
| The mathlib Community (2020) | `lem:sum-succ` |

The *Concrete Mathematics* entry is the same source the theorem records
structurally in its `origin` / `origin_details` (step 2 of the build) — the
citation is the prose-level link, the `origin` is the machine-readable one.

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
  `related_to` edge;
- two **comments** (a debugging progression, each with a `--title`) on the still-
  `sorry` lemma, stored as attachments under `nodes/<id>/comment-N.md`;
- two **reviews**, each a Maths good/bad + comment and/or a Lean good/bad +
  comment (`--maths`/`--maths-comment`, `--lean`/`--lean-comment`) — one on
  the lemma (maths good, lean bad: unfinished proof), one on the theorem
  (maths good only).

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
the YAML. Only three types exist: a statement's and a proof's `\uses` both
generate the same hard `uses` edge (deduped to one per pair), so there's no
separate "statement vs proof dependency" to track.

| class | type | source | merges in union view? |
|-------|------|--------|:---:|
| hard | `uses` (statement/proof `\uses`) | generated | no |
| identity (soft) | `formalizes` (`\lean`) | generated | **yes** |
| associative (soft) | `related_to` | authored | no |

(Comments aren't edges — they're attachments under `nodes/<id>/`.)
