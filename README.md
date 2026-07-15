# hgraph

A plain-files semantic graph for autoformalization. Nodes and edges are
Markdown/YAML files you (or an agent) write through a CLI, or that `sync`
generates from a leanblueprint `.tex` + your Lean sources — no database, no logs.
The files *are* the graph; git versions them.

**[Live demo →](https://axeldlv00.github.io/hgraph/)** — the `gauss` example rendered
to an interactive blueprint dashboard (built by `bash examples/gauss/build.sh`).

```
<project>/hgraph/
  nodes/<id>.md            one file per node: YAML header (metadata) + content body
  nodes/<id>/              sibling dir, created only if the node has attachments
    comment-1.md             a comment: {author, created, updated} header + body
  edges/<src>__<tgt>.md    one file per ordered pair: YAML header (type, hard, note)
  edges/<src>__<tgt>/      sibling dir, created only if the edge has attachments
```

Every node id is a uniform opaque hash: synced nodes hash their `\label` /
Lean `decl`, hand-added nodes hash a `--key` (default: the title). Reference any
of them without knowing the hash via `label:…` / `decl:…` / `key:…`. Edge files
are named by their endpoint pair only — the edge **type lives in the YAML**, not
the filename. Comments are *attachments* under a node's sibling directory, not
extra nodes in the graph.

## Model

- A **node** is an artifact: an informal statement (`type: tex`), a Lean
  declaration (`type: lean`), a proof, a source quote, a comment. Metadata lives
  in the YAML header; the mathematical content is the body.
- **Edges** are typed and fall into three classes:
  - **hard** — a dependency (`depends_on`). This is the DAG you schedule on.
  - **identity (soft)** — `formalizes`, `informal_of`, `same_as`: two nodes are
    the *same* object in different forms.
  - **associative (soft)** — `quote`, `related_to`: related but *distinct*.
- **Comments** ("tried simp, failed because …") are *attachments* under a node's
  sibling directory (`nodes/<id>/comment-N.md`) — persistent failure memory that
  travels with the node, not extra nodes in the graph.

## Install

```bash
pip install -e .          # provides the `hgraph` command (needs PyYAML)
```

Use the `hgraph` command, not `python -m hgraph`: the latter breaks inside a
project dir because the `hgraph/` **data** directory shadows the package.

## Sync — blueprint + Lean as the reference

Rather than hand-build the graph, point `sync` at a leanblueprint `.tex` and your
Lean sources; it parses them and fills in the derived structure:

```bash
hgraph sync --blueprint blueprint/blueprint.tex --lean Lean
hgraph sync                       # no flags → read the paths from hgraph/config.yaml
```

Create `<project>/hgraph/config.yaml` so a bare `sync` knows where to look:

```yaml
blueprint: blueprint/blueprint.tex   # paths are relative to the project root
lean: [Lean]
```

- **Two independent node populations.** A blueprint item is keyed on its LaTeX
  `\label`; a Lean declaration on its fully-qualified name. There's no 1-to-1
  correspondence — `\lean{…}` links them with a many-to-many `formalizes` edge.
  Both ids are `sha1("<kind>:<key>")[:12]` — uniform and opaque (as are
  hand-added nodes, which hash a `--key`); reference a node by `label:<label>`,
  `decl:<fqname>`, or `key:<key>` and the CLI resolves the hash.
- **Edges come from the macros.** `\lean{}` → `formalizes`; a statement `\uses{}`
  → `depends_on`; a proof `\uses{}` → `uses`.
- **Formalization state.** Every node carries `lean_status: mathlib_ok | lean_ok
  | sorry | empty`. A Lean node reads it from its source (`sorry` → `sorry`);
  a tex node aggregates it from the Lean node(s) it `formalizes` — recomputed
  each sync, so it can't drift — with `\mathlibok` → `mathlib_ok` plus a
  `mathlib_name`. Every node also gets `author` / `created` / `updated`
  (bumped only on real change); Lean nodes carry `file` and `docstring`.
- **Owned vs authored.** `sync` writes only the fields it owns (title,
  content_type, body, the derived flags) and edges it tagged `generated:`.
  Everything a human/agent added — `origin`/source, `tags`, `status`, comments,
  hand-drawn edges — is preserved, so re-running `sync` is idempotent. A `\label`
  that vanishes is flagged `stale: true`, never deleted.

## CLI

Most of the graph comes from `sync`; the CLI is for the authored layer on top.
Reference nodes by `label:`/`decl:`/`key:` — you never type a hash.

```bash
hgraph add node   --title "théorème central limite" --type tex --origin book
hgraph add node   --title "CLT (Lean)" --key clt-lean --type lean --content 'theorem clt : ...'
hgraph add edge   key:clt-lean decl:MeasureTheory.integral --type depends_on
hgraph add comment key:clt-lean --author agent --content 'MeasurableSpace instance missing'

hgraph get        key:clt-lean          # content + related + deps + ancestors + comments
hgraph modify node key:clt-lean --set status=proved
hgraph ancestors  key:clt-lean --names  # transitive dependencies
hgraph view union                       # tex | lean | union   (+ --dot for Graphviz)
hgraph delete node key:clt-lean         # cascades to its edges
```

**Query, don't scroll.** Every listing takes `--limit N` (show only the first N)
and `--json` (structured output for agents/scripts); `list` is a small query
engine over the authored + derived fields:

```bash
hgraph stats                            # totals + breakdown by type / lean_status / status
hgraph list --type tex --lean-status sorry --limit 20      # the next 20 to formalize
hgraph list --tag flagship --sort chapter                  # by document order
hgraph list --match "central limit" --json                 # full-text over title+content
hgraph list --generated manual         # only hand-added nodes  (blueprint | lean | manual)
hgraph list --stale                    # nodes whose source \label / decl vanished
hgraph edges --source key:clt-lean --hard --json           # its dependency edges (with ids)
hgraph get key:clt-lean --json                             # the whole neighbourhood as JSON
```

**Walk the graph: what's proven, what's next.** `lean_status` is *local* (a node's
own Lean code). To know what is *fully* done and what is *ready to work on*, the
CLI closes over the hard-dependency DAG:

```bash
hgraph frontier                         # the actionable list: every node whose
                                        # prerequisites are all closed, ranked by
                                        # how much finishing it unblocks downstream
hgraph frontier --type tex --limit 20 --json     # for an agent to pick the next task
hgraph list --state ready               # same frontier, unranked  (also: blocked | closed
hgraph list --state blocked --type tex  #  | formalized_open | informal)
hgraph stats                            # + a closure line: closed / ready / blocked /
                                        #   formalized-but-open / informal counts
```

A node is **closed** when it *and* its whole prerequisite closure are formalized;
**ready** when it isn't done yet but every prerequisite is closed (workable now);
**blocked** when a prerequisite is still open; **formalized_open** when its own Lean
is done but something upstream isn't. `frontier` is the "what should I prove next"
query — ready nodes sorted by downstream unlocks (cycle-safe, computed in one pass).

**One edge per ordered pair.** The edge type lives in the YAML, so a pair holds
one edge; `add edge` onto an occupied pair is refused unless you pass `--replace`
(so it can't silently drop a dependency under a soft link). A `label:`/`decl:`/`key:`
reference matching several nodes is likewise rejected as ambiguous rather than
resolving to an arbitrary one. Remove a note with `hgraph delete comment <node>
--n 2` / `delete review` (the number is shown by `get`).

Runs against `./hgraph`; use `--root <dir>` to point elsewhere.

## Three views

- **tex** — informal nodes, expanding to their soft-linked formalizations.
- **lean** — the formal side, primary.
- **union** — every identity-linked cluster contracts to one conceptual node
  (1 informal ↔ N formal ⇒ one node); dependencies run between the clusters.

## Dashboard

A modern, light rendering of the **full blueprint document** — the prose,
**numbered** chapters/sections/statements, and proofs — enriched with the graph:

- reads the blueprint (from `--blueprint` or `hgraph/config.yaml`) and renders it
  chapter by chapter: numbered headings, prose (math, lists, quotes, `\emph`…),
  each statement in a **tagged** box (`Thm 1.2`), collapsible proofs;
- cross-references and `\uses` render as **numbered links** (`Lem 3.4`), not raw
  labels; **hover** one to preview the target statement; **click** it to jump to
  its chapter and centre it;
- each statement carries its `lean_status`, a **reviewed / not-reviewed** badge
  (+ verdict), and its Lean declaration(s) with **syntax-highlighted code**
  (hover the Lean name to preview it);
- each statement carries compact **tags** — `uses N · used by N` (click for a
  local dependency graph), `L∃∀N · N` (click for the `\lean{}` declarations +
  code), and **★ N reviews** / **💬 N comments** buttons that list the notes
  (author + created/updated date; reviews are just good/bad) and — under
  `hgraph serve` — let you **write a new one inline**; popups pin on click and
  dismiss on outside-click (there is no separate detail drawer);
- statement boxes are colored by **kind** (def/thm/lemma/…, like a real
  blueprint); the status badge is **green (lean ok) / blue (mathlib) / red
  (sorry) / grey (none)**, and reviewed is a **violet ✓** (a check, not a colour
  that clashes with the status map);
- the header is just the title + progress bar; a **left panel** holds search,
  status filters, front-matter links (**Overview / Summary / Bibliography /
  Dependency graph**) and a **hierarchical table of contents** (chapters + their
  sections, current chapter expanded, each section showing a row of status
  squares). Each chapter opens with a collapsible **chapter-contents overview**
  (its sections, each with its own status squares), and a right **"in this
  chapter"** panel gives a *miniature blueprint* (mini statement cards);
- **Blueprint summary**: an FLT-style progress dashboard — *ready now* (unblocked
  frontier), *fully closed* (self + transitive deps done), *actionable
  priorities*, *current blockers* (sorries) — with a ranked "ready next" list
  whose entries render as **statement boxes** (kind left-bar, hover for the LaTeX
  statement), and a per-chapter table;
- **Blueprint bibliography**: entries parsed from any `.bib` beside the blueprint,
  formatted with author/year/venue/pages and a **cited-from** back-reference
  list; `\cite{…}` in the text links to it;
- a full-project **dependency graph** rendered **FLT-blueprint-style with Graphviz**
  (client-side via d3-graphviz + WASM, loaded from a CDN): every node a **named box**
  with its title inside (**rectangle = definition, ellipse = theorem/lemma**),
  **border = statement status** (blocked / ready / formalized), **fill = proof status**
  (not ready → ready → Lean-incomplete → locally formalized → +deps complete),
  **spline arrows** whose style separates statement (solid) from proof (dashed) deps,
  and a **Legend** panel. Two views: **Graphviz · clustered** — the whole graph with
  one labelled `subgraph cluster` per chapter — and **Group view · chapters**, a
  chapter-level DAG (one node per chapter, sized/coloured by progress) where **clicking
  a chapter drills into** its own clustered subgraph; the **focus** dropdown does the
  same for any chapter. **Selecting** a node highlights it and opens it in the side
  panel. The side-panel mini dependency graph clicks through to **select and centre**
  the node in the main graph. If the Graphviz libraries can't be fetched (offline, e.g.
  a `--self-contained` export) the graph **falls back to a built-in canvas layout**.
  Click a node to load it into an **always-open side panel** (statement, Lean, deps,
  reviews & comments) beside the graph;
- an **overview** panel: a minimap of every statement as a colored square, per
  chapter (reviewed marked with a ✓) — the global sorry/lean picture at a glance;
- KaTeX math with the project's `\Spec`/`\Pic`/… **auto-discovered** from the
  blueprint's `.sty`/`.tex` (no config); `--macros file` can still override.

```bash
hgraph dashboard --out site.html --self-contained   # static export for GitHub Pages
hgraph serve --port 8000                             # same page, live, with write-back
```

- **`dashboard`** writes one static HTML file (open it directly, serve the
  folder, or drop it on GitHub Pages). `--self-contained` inlines KaTeX + fonts
  so it renders offline.
- **Graphviz (optional, recommended for large graphs).** If the `dot` binary is on
  PATH at build time, the full dependency graph's layout is **precomputed** and the
  positioned SVG embedded, so the graph opens instantly with no CDN fetch or
  client-side WASM layout. Without `dot` it falls back to laying out in the browser.
  Install with `dnf install graphviz` / `brew install graphviz`.
- **`serve`** runs a local server where you can **add reviews and comments from
  the page** — they're written straight into the graph (like `hgraph add
  review`), so a re-`sync` keeps them.

## Examples

- `bash examples/gauss/build.sh` — a small worked Gauss-summation graph: sync,
  layer on provenance / comments / reviews, re-sync (idempotent), then `get`,
  `ancestors`, `union`. See [examples/gauss/](examples/gauss/).

## Status

First working slice: storage, full CLI, queries, static (text/DOT) views, and
`sync` from a leanblueprint `.tex` + Lean sources. Next: an interactive clickable
viewer (expand soft links; switch tex/lean/union).
