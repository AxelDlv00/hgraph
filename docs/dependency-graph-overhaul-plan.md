# Dependency-Graph & Content-Structure Overhaul — Implementation Plan

Status: **proposal for review** (2026-07-11). Grounds the "3-tier dependency graph"
memo against the actual `hgraph` codebase and lays out a phased build. Nothing here
is built yet except Phase 0, which is done.

---

## Update — 2026-07-13: granularity axis (group + level) shipped as a stub

Built on top of the existing renderer (tested on the live `OpenGA-Horizon/Poincare`
graph, 762 nodes in the doc path):

- **`group` + `level` on every entry** (`dashboard._assign_groups_levels`). Values
  authored on the node / written by a future `hgraph extract` AI pass **always win**;
  missing ones get a heuristic stub — `group` by single-level Louvain modularity
  (adaptive resolution, small-cluster merge, capped to ~30 communities → 44 groups on
  Poincaré), `level` by how depended-on a node is (`coarse` = top ~12%, `medium` =
  main-result kind, else `fine`). Computed at **build time** from the synced graph, so
  it survives `build.sh`'s wipe-and-resync.
- **Two new graph views** precomputed by `dot` (`layout.py`): **Clustered · by group**
  and **Groups · overview** (one super-node per group, click to drill into its cluster).
  `grp<N>` overview ids ↔ `cluster_<N>` cluster ids share the group index.
- **Detail (level) filter** in the graph toolbar — coarse / coarse+medium / all — hides
  finer nodes across the canvas and precomputed-SVG views (`GM.visArr` / `gmVisible`).

Still a stub for clustering quality; the AI `extract` pass (Phase 4) replaces the
heuristic `group`/`level`. Not browser-tested end-to-end here (no display): verified by
build success, embedded-SVG structure, index correspondence, and JS `node --check`.

## 1. Goal

Turn the dependency graph from a decorative add-on into the site's core navigation:

- fix the two concrete pain points (local mini-graph readability; global graph is
  unusably slow to load);
- add the missing structural layers (medium-grained clusters, a topological
  "learning path" reading mode);
- make dependency extraction AI-assisted (incl. implicit deps), on top of the
  existing `sync`-from-blueprint pipeline;
- keep everything in the plain-files model — no database, git versions it.

---

## 2. What already exists (do NOT rebuild)

The memo describes a 3-tier system; much of it is already in `hgraph`. Mapping the
memo's asks onto the current code:

| Memo item | Already in hgraph | Where |
|---|---|---|
| Fine-grained theorem/def graph | ✅ full graph, box-per-node, def=rect/thm=ellipse, status colours | `dashboard.py` `gmDot`, `gmStatuses` |
| Coarse module map | ⚠️ partial — chapter clustering + a chapter-level "group view" DAG with drill-in | `gmDot` `subgraph cluster_*`, `gmDotGroups`, `gmDrillChapter` |
| Upstream/downstream side panel | ✅ side panel + mini graph (uses ↑ / used by ↓) | `nodePanel`, `depGraph` |
| Topological "gap-free" order | ✅ closure + frontier ranking (cycle-safe, one pass) | `analysis.py`, `hgraph frontier` |
| Full-graph dependency tracing | ✅ transitive ancestors | `graph.py`, `hgraph ancestors` |
| Explicit-citation extraction | ✅ `\uses{}` → `depends_on`/`uses`, `\lean{}` → `formalizes` | `sync.py` |
| Manual edge add/remove + write-back | ⚠️ partial — `serve` already writes reviews/comments back into files | `server.py`, `cli.py add edge` |
| Layered lazy loading / precomputed layouts | ❌ not yet — layout is client-side WASM each open | see Phase 1 |
| Medium-grained cluster layer | ❌ not yet | see Phase 3 |
| AI implicit-dependency detection | ❌ not yet | see Phase 4 |
| Learning-path reading mode | ❌ ordering exists, no reading UI | see Phase 5 |

**Net-new work** is therefore: precomputed layouts (perf), a medium cluster layer,
AI dependency extraction, and a learning-path reading mode + curation UI. The rest
is refinement of existing machinery.

---

## 3. Root-cause of "the global graph is unusable"

Two independent costs, both real (measured on `examples/jacobian`, ~1850 statements):

1. **13.7 MB static HTML.** `dashboard.py` inlines every node body + all Lean source
   as one JSON blob (`DATA`). The browser parses all of it before first paint —
   independent of the graph.
2. **Client-side WASM layout on every open.** `gmDot()` emits *all* ~1850 nodes
   (clustered by chapter) and hands the whole DOT to `d3-graphviz` (fetched from a
   CDN) to lay out from scratch each time the modal opens. Graphviz-in-WASM laying
   out ~1850 nodes + cluster constraints is the multi-second stall.

The `graphviz` view is the **default** layout, so opening the modal always pays #2.

---

## 4. Architecture: one dataset, layouts computed at build

Keep the memo's "one unified dependency dataset, three layers" principle. The dataset
already exists (the files). The change is **where layout happens**: move it from the
browser to build time.

```
build time (Python)                          load time (browser)
─────────────────                            ──────────────────
graph files ──► Analysis (closure/status) ──► node/edge/status model
                          │                          │
                          ├─ emit DOT per layer       └─ (unchanged) statement pages
                          │   (full / group / cluster)
                          └─ dot -Tsvg  ──► positioned SVG  ──► inline into HTML
                                                                     │
                                                    swap "renderDot via WASM"
                                                    for "innerHTML = precomputed SVG"
                                                    + run the SAME gmGvizPostRender wiring
```

The elegant part: Graphviz emits `<g class="node"><title>ID</title>…>`. The existing
`gmGvizPostRender` already wires clicks/hover/filter by matching `<title>` to node id.
It does not care whether the SVG came from WASM or from a build-time `dot`. So the
interactive layer is **reused verbatim**; only the source of the SVG changes.

---

## 5. Phased plan

### Phase 0 — Local mini-graph fix ✅ DONE

`depGraph` in `dashboard.py`:
- node label is now the **title** (`plainTex`, wrapped to 2 lines), not `Def 3.4`;
- same convention as the big graph: rect=def/notation, ellipse=thm/lemma, border =
  statement status, fill = proof status (`entryStyle`);
- every upstream/downstream node carries `data-id`, so **hover shows the full
  statement** and click opens it in the graph.

Known limitation: hover preview is suppressed when the mini-graph sits inside an
already-pinned popup (the "uses N" tag popup); it works in the side panel. Fixable
later if it matters (nested-popup hover).

### Phase 1 — Make the global graph open instantly ✅ IMPLEMENTED

**Goal:** graph opens instantly. Delivered in two layers, so it works **with no extra
dependency** and gets even nicer if graphviz is installed:

- **No graphviz (default).** The graph now defaults to a pure-JS canvas "layered"
  (Sugiyama) layout — **measured at 15 ms for the full 1868-node / 4337-edge jacobian
  graph** — with no CDN fetch and no WASM. The old client-side Graphviz-in-WASM layout
  (the multi-second stall) is now **opt-in** via the layout dropdown, not the default.
- **With graphviz (optional upgrade).** If `dot` is on PATH at build, `hgraph/layout.py`
  runs it once and embeds the positioned **clustered** SVG (`GVSVG`); the JS renders it
  directly with a self-contained pan/zoom. Install with `sudo dnf install -y graphviz`.

Both paths avoid the CDN and the per-open layout compute. **Verified:** DOT emission
matches the JS byte-for-byte; canvas layout timed at 15 ms on real data; no regression
when `dot` is absent. Not browser-tested end-to-end here (no display), but the canvas
path is the project's existing offline renderer, now promoted to default.

Design (as built):

1. New Python module `hgraph/layout.py` (or extend `render.py`):
   - reuse `analysis.py` for closure/`_closed`/status so border+fill match the JS
     exactly (port `gmStatuses` semantics: statement status from lean_status + deps,
     proof status from closure);
   - build the same DOT strings Python-side that `gmDot` / `gmDotGroups` build now;
   - shell out to `dot -Tsvg` (detect `dot` on PATH via `shutil.which`);
   - return the SVG string(s).
2. `dashboard.py` embeds, at build time, the **full clustered** SVG and the
   **group-view** SVG (the two expensive layouts). Per-chapter drill-in stays on the
   cheap client path (≈50 nodes) — or is precomputed lazily; decide after measuring.
3. JS: in `gmRenderGviz`, if a precomputed SVG for the current mode exists, set
   `host.innerHTML = SVG` and call `gmGvizPostRender()` directly — skip
   `gmEnsureGviz`/`renderDot` entirely. Pan/zoom: attach a lightweight d3-zoom or a
   small self-contained pan/zoom (avoids the CDN d3 dependency on the hot path).
4. **Fallback preserved:** if `dot` is absent at build, embed nothing; JS falls back
   to today's WASM path, and offline export falls back to the canvas Sugiyama layout
   (`gmSugiyama`) exactly as now. No regression when graphviz isn't installed.

**Dependency:** requires `graphviz` (`dot`) on the build machine. *Not currently
installed here* — add to `pyproject.toml` extras + README, and `dnf install graphviz`
/ `brew install graphviz` for local builds. Fully optional at runtime (fallback).

**Acceptance:** jacobian graph modal opens in < 300 ms with no network; identical
node styling; click/hover/filter/select all still work.

### Phase 2 — Trim the 13.7 MB payload / layered lazy loading

Independent of Phase 1; tackles the whole-page parse cost.

- Split the heavy fields (node `body`, Lean `code`) out of the inlined `DATA` blob
  into a sidecar `data.json` fetched on demand; the initial HTML carries only what
  the table of contents + graph need (title, kind, status, deps).
- Keep `--self-contained` as the single-file escape hatch (stays big by design for
  offline/GitHub-Pages drop-in); make the **default** export the split, lazy form.
- Under `serve`, this is already natural (`/api/graph`); extend to `/api/node/<id>`
  for bodies/Lean on click.

**Acceptance:** default export first-paints without parsing megabytes; statement
bodies/Lean load on navigation.

### Phase 3 — Medium-grained cluster layer

The genuinely missing tier: groups of 3–5 related statements between chapter and
statement granularity.

- Data model: represent a cluster as a first-class node (`type: cluster` / a new
  `content_type: cluster`) whose membership is edges (`contains` / reuse `related_to`),
  OR as a lightweight `cluster:` field on member nodes. Prefer explicit cluster nodes
  so they carry a title/description and can be curated and version-controlled like any
  node. Add to `schema.yaml`.
- Seeding: AI-cluster (Phase 4) proposes membership; a human refines. Store as
  `generated: ai` so re-runs stay idempotent (same owned-vs-authored rule as `sync`).
- Rendering: a third layout mode between "group view" (chapters) and full — one node
  per cluster, edges = inter-cluster prerequisites, click drills into the cluster's
  statements. Reuses the Phase 1 precompute + drill-in machinery.

### Phase 4 — AI dependency & cluster extraction (Fable 5)

- New command `hgraph extract` (Claude API, model `claude-fable-5`): reads node bodies
  + Lean, proposes (a) **implicit** `depends_on` edges the `\uses{}` macros miss, and
  (b) cluster membership for Phase 3.
- Write proposals as edges tagged `generated: ai` with a `note:` justification, so
  they're visible, revertible, and never stomp authored edges. `sync` idempotency
  rules already cover this ownership split — extend the "owned fields" set to include
  `generated: ai`.
- Guardrails: AI only *proposes*; nothing lands without the curation pass (Phase 6).
  Run topological sort (existing `frontier`/closure) over the augmented graph to
  surface cycles the AI may introduce, and flag them for review.
- See `claude-api` skill for model id / SDK usage before wiring the API.

### Phase 5 — Topological "learning path" reading mode

- The ordering already exists (`analysis.py` closure + `frontier` ranking). Add a
  reading UI: a linear, dependency-respecting sequence as an alternative to the
  chapter-order table of contents — "chapter mode ⇄ dependency-driven mode" toggle in
  the left panel (the memo's core ask).
- Each entry links to its statement; upstream prereqs shown inline. Pure
  presentation over data we already compute.

### Phase 6 — Curation / manual-edit interface

- `serve` already write-backs reviews/comments (`server.py` POST handlers). Add
  `POST /api/edge` (add/remove/retype) and `POST /api/cluster` to accept edits from
  the page, writing edge files exactly like `cli.py add edge` (respecting the
  one-edge-per-pair `--replace` rule).
- UI: on the fine graph, an "edit dependencies" affordance to confirm/reject AI
  proposals (Phase 4) and hand-correct edges — the memo's "manual correction
  interface".

---

## 6. Data-model changes (schema.yaml)

- `node.content_type`: add `cluster` (Phase 3).
- `node.origin`: `ai` already allowed. Good.
- `edge.type`: add `contains` (cluster membership) if clusters are node-based.
- `edge.generated`: allow `ai` (Phase 4) alongside `blueprint`.
- Ownership rule: `sync` and `extract` own only `generated: blueprint|lean|ai`
  edges/fields; authored edges (no `generated:`) are never touched. Preserves
  idempotency.

---

## 7. Risks & open questions

- **graphviz build dependency (Phase 1).** Adds a system dep. Mitigated by full
  runtime fallback, but CI/build docs must install it. Confirm the build environment.
- **Payload split vs single-file export (Phase 2).** `--self-contained` is a feature
  (drop one file on GitHub Pages). Keep it; change only the default. Confirm this is
  acceptable.
- **AI edge quality (Phase 4).** Implicit-dependency detection will have false
  positives; the curation gate (Phase 6) is load-bearing. Don't auto-merge.
- **Cluster granularity (Phase 3).** "3–5 statements" is a heuristic; needs iteration
  with a real chapter. Start with one chapter as a pilot.
- **Cycle introduction.** AI or manual edges can create cycles; the topological pass
  must detect and surface them (closure is already cycle-safe, but the *reading order*
  needs a clean DAG).

---

## 8. Suggested sequencing

1. **Phase 1** (perf) — highest user-visible impact, greenlit, self-contained.
2. **Phase 2** (payload) — completes the "usable global graph" goal.
3. **Phase 3 + 4** pilot on one chapter — validate clusters + AI extraction small.
4. **Phase 5** (learning mode) — cheap once 3/4 exist.
5. **Phase 6** (curation UI) — needed before AI edges are trusted at scale.

Phases 1–2 deliver "the graph is usable" without touching the content model. Phases
3–6 deliver the memo's larger "core navigation system" vision, gated on a pilot.
