# hgraph

![python](https://img.shields.io/badge/python-3.9%2B-blue)
![status](https://img.shields.io/badge/status-beta-orange)

A plain-files semantic graph for autoformalization. Nodes and edges are
Markdown/YAML files you (or an agent) write through a CLI, or that `sync`
generates from a leanblueprint `.tex` + your Lean sources — no database, no
logs. The files *are* the graph; git versions them.

**[Live demo →](https://axeldlv00.github.io/hgraph/)** — a landing page over
two worked examples (`gauss`, `triangular`), each an interactive blueprint
dashboard.

> [!NOTE]
> First working slice: storage, full CLI, sync, closure/frontier queries, and
> the dashboard/site UI. See [Status](#status).

## What this is

A node is an artifact — an informal statement (`type: tex`), a Lean
declaration (`type: lean`), a proof, a source quote — stored as one Markdown
file: a YAML header for metadata, the mathematical content as the body. An
edge is its own small file per ordered pair (`<source>__<target>.md`); the
type lives in the YAML, not the filename. Comments and reviews are
*attachments* under a node's sibling directory, not extra nodes.

```
<project>/hgraph/
  nodes/<id>.md            one file per node: YAML header (metadata) + content body
  nodes/<id>/              sibling dir, created only if the node has attachments
    comment-1.md              a freeform note: {author, date, title} header + body
    review-1.md                a Maths/Lean good-or-bad verdict (see Fields)
  edges/<src>__<tgt>.md    one file per ordered pair: YAML header (type, hard, note)
```

Every node id is a uniform opaque hash: synced nodes hash their `\label` /
Lean `decl`; hand-added nodes hash a `--key` (default: the title). Reference
any of them without knowing the hash via `label:…` / `decl:…` / `key:…`.

Edges are typed and fall into three classes — there's no more granularity
than this, because `sync` only ever needs to express two relationships
(`\uses` and `\lean`):

- **hard** — `uses` (from `\uses{}`, statement or proof alike). This is the
  DAG you schedule on.
- **identity (soft)** — `formalizes` (from `\lean{}`): two nodes are the
  *same* object in different forms; these merge in the union view.
- **associative (soft)** — `related_to`: related but *distinct* — quotes,
  alternative proofs, anything hand-drawn that isn't a dependency.

## Fields

Ownership: **[derived]** — written only by `sync`, never touched otherwise;
**[authored]** — written by a human/agent (CLI, dashboard, or by hand) and
left untouched by `sync`. Re-running `sync` is therefore idempotent.

**Node** (`nodes/<id>.md` header)

| field | values | owner |
|---|---|---|
| `id` | `sha1("<kind>:<key>")[:12]` | derived |
| `label` / `decl` / `key` | the blueprint `\label` / Lean fq-name / hand-added `--key` | derived / derived / authored |
| `generated` | `blueprint` \| `lean` (absent on hand-added nodes) | derived |
| `title` | text (required) | derived when synced, else authored |
| `author`, `created`, `updated` | text / ISO timestamp | derived |
| `type` | `tex` \| `lean` \| `md` | authored |
| `content_type` | `statement` \| `definition` \| `theorem` \| `lemma` \| `proposition` \| `corollary` \| `proof` \| `example` \| `remark` \| `conjecture` \| `quote` \| `instance` | derived when synced, else authored |
| `status` | `false` \| `failed` \| `draft` \| `verified` \| `built` | authored |
| `lean_status` | `lean_ok` \| `mathlib_ok` \| `sorry` \| `empty` | derived |
| `mathlib_name` | list of Mathlib decl names | derived |
| `stale` | `true` (the source `\label`/`decl` vanished; never auto-deleted) | derived |
| `origin` | `book` \| `article` \| `preprint` \| `textbook` \| `lecture-notes` \| `repository` \| `ai` \| `human` \| `unknown` | authored |
| `origin_details` | `{work, author, edition, version, chapter, section, page, year, url}` | authored |
| `lang` | `en` \| `fr` \| `de` \| `other` | authored |
| `tags` | list of free-form labels | authored |
| `docstring`, `file` | the Lean decl's `/-- … -/` doc, its source path | derived, Lean nodes only |

**Attachment** (`nodes/<id>/{comment,review}-N.md`)

| field | values | kind |
|---|---|---|
| `author`, `date` | text / ISO timestamp | both |
| `title` | short heading | comment |
| `maths_verdict`, `maths_comment` | `good` \| `bad`, text | review (either axis optional, at least one required) |
| `lean_verdict`, `lean_comment` | `good` \| `bad`, text | review |

**Edge** (`edges/<source>__<target>.md` header)

| field | values | owner |
|---|---|---|
| `source`, `target` | node ids (required) | — |
| `type` | `uses` (hard) \| `formalizes` (identity, soft) \| `related_to` (associative, soft) | derived when synced, else authored |
| `hard` | `true`/`false`, auto-filled from `type` | derived |
| `generated` | `blueprint` (absent on hand-drawn edges) | derived |
| `note` | text | authored |

## Install

```bash
pip install -e .          # provides the `hgraph` command (needs PyYAML)
```

> [!IMPORTANT]
> Use the `hgraph` command, not `python -m hgraph`: the latter prepends the
> current directory to the import path, so inside a project dir the local
> `hgraph/` **data** directory shadows the real package and `-m` fails to
> find `hgraph.__main__`.

## Sync — blueprint + Lean as the reference

Point `sync` at a leanblueprint `.tex` and your Lean sources; it parses them
and fills in the derived structure. `\lean{}` → `formalizes`; `\uses{}`
(statement or proof) → `uses`; `\mathlibok` → `mathlib_ok` + `mathlib_name`.

```bash
hgraph sync --blueprint blueprint/blueprint.tex --lean Lean
hgraph sync                       # no flags → read the paths from hgraph/config.yaml
```

Two independent node populations, joined many-to-many by `formalizes`: a
blueprint item is keyed on its `\label`, a Lean declaration on its
fully-qualified name. `sync` writes only the fields it owns (see Fields
above); everything a human/agent added is preserved, so re-running it is
idempotent, and a vanished `\label`/`decl` is flagged `stale`, never deleted.

## CLI

Most of the graph comes from `sync`; the CLI is for the authored layer on
top. Runs against `./hgraph`; use `--root <dir>` to point elsewhere.

> [!TIP]
> Reference nodes by `label:<label>`, `decl:<fqname>`, or `key:<key>` — you
> never type a hash, and an ambiguous reference is rejected rather than
> resolved arbitrarily.

```bash
hgraph add node    --title "théorème central limite" --type tex --origin book
hgraph add edge    key:clt-lean decl:MeasureTheory.integral --type uses
hgraph add comment key:clt-lean --author agent --content 'MeasurableSpace instance missing'
hgraph add review  key:clt-lean --author agent --maths good --lean bad --lean-comment 'proof incomplete'

hgraph get         key:clt-lean          # content + related + deps + ancestors + notes
hgraph modify node key:clt-lean --set status=verified
hgraph ancestors   key:clt-lean --names  # transitive dependencies
hgraph view union                        # tex | lean | union   (+ --dot for Graphviz)
hgraph delete node key:clt-lean          # cascades to its edges
```

**Query, don't scroll.** Every listing takes `--limit N` and `--json`;
`list` is a small query engine over the authored + derived fields:

```bash
hgraph stats                                                # totals + closure + provenance breakdown
hgraph list --type tex --lean-status sorry --limit 20       # the next 20 to formalize
hgraph list --tag flagship --sort chapter --json            # by document order, for a script
hgraph list --match "central limit"                         # full-text over title+content
hgraph list --generated manual                              # only hand-added nodes
hgraph list --stale                                          # nodes whose source vanished
```

**Walk the graph: what's proven, what's next.** `lean_status` is *local*; the
CLI also closes over the hard-dependency DAG to tell you what's fully done
and what's workable now:

```bash
hgraph frontier --type tex --limit 20 --json     # ranked "prove this next", for an agent
hgraph list --state ready                         # same frontier, unranked
```

A node is **closed** when it and its whole prerequisite closure are
formalized; **ready** when every prerequisite is closed but it isn't yet
(workable now); **blocked** when a prerequisite is still open;
**formalized_open** when its own Lean is done but something upstream isn't.

One edge per ordered pair — `add edge` onto an occupied pair is refused
unless you pass `--replace`. A `label:`/`decl:`/`key:` reference matching
several nodes is rejected as ambiguous rather than resolving arbitrarily.

## The site

There is no separate per-project "dashboard" artifact — one project or many,
`hgraph site` is the only output, a single-page app that hash-routes
client-side between the landing page (`#/`) and a project's statements
(`#/<root>`):

```bash
hgraph site                        # writes _site/: index.html + assets/ + one <root>/data.json per project
hgraph serve --port 8000           # the same app, live — review/comment write-back, no export step
```

Everything generated lands under `_site/` (override with `--out`), so it never
mixes into your sources — and that directory *is* the deployable site.

`site` writes a landing page — cards grouped under a heading per `category`
if the manifest sets one, above an optional overview fragment (`.md` for a
plain blurb; `.html` if you need custom boxes/diagrams — hgraph pipes it
through unmodified either way) — plus each project's statements (Lean code,
dependencies, reviews/comments) as its own `data.json`. This is the standard
output **even for a single project**: with no `--manifest`, it looks for a
workspace `config.yaml` and falls back to synthesizing a solo-project page
from `hgraph/config.yaml`'s `site:` block (see Config below) — still a home
page + overview + a click into the project, just one card.

> [!NOTE]
> `site` is a React/Vite frontend (`frontend/`), pre-built and shipped with
> the package — `pip install hgraph` never requires Node.js. Python only
> ever emits two JSON shapes (the landing data, and a project's statements +
> Lean + deps + reviews); every bit of rendering — KaTeX math, the
> interactive dependency graph, hover-previews, search, the bibliography,
> the review form — happens client-side. See `frontend/README-DEV.md` if
> you're changing the frontend itself.

`serve` auto-detects a workspace the same way `site` does (a `config.yaml`
next to the project directories, or `--manifest`): pointed at one project it
serves that project alone (still with its own one-card landing page);
pointed at a workspace root it serves the whole site — the landing data at
`GET /api/site`, each project's at `GET /<root>/data.json`, both cached and
rebuilt automatically whenever the underlying files change, so they never go
stale. One process, one port, either way.

**Reviewing.** Live (`hgraph serve`), the review form under a statement POSTs
straight into the graph — exactly like `hgraph add review`. A **static**
export (no server, e.g. GitHub Pages) instead offers "Suggest on GitHub": it
builds a prefilled `github.com/<repo>/issues/new` link from the same
Maths/Lean form and opens it in a new tab — no backend needed, just a `repo:
owner/name` in the `site:` config block. Comment fields are capped
client-side to stay well under the browser/GitHub URL length limit.

## Config

Two levels, both named `config.yaml`:

- **Project** — `<project>/hgraph/config.yaml`: where `sync` finds the
  sources, plus an optional `site:` block for a solo project's landing page.

  ```yaml
  blueprint: blueprint/blueprint.tex   # paths are relative to the project root
  lean: [Lean]
  site:
    title: My project
    subtitle: A one-line description
    overview: overview.md              # optional, Markdown
    repo: owner/name                   # optional — enables the GitHub-issue review link
  ```

- **Workspace** — a `config.yaml` next to several project directories, read
  by a bare `hgraph site` with no `--manifest`:

  ```yaml
  title: My workspace
  overview: overview.md              # optional, same .md/.html rule as above
  projects:
    - name: Project A
      root: a                          # dir containing a/hgraph/
      category: Group name             # optional — groups cards under a heading
      blurb: One line about it.
  ```

## Examples

- [`examples/gauss/`](examples/gauss/) — the `sync` workflow end to end:
  blueprint + Lean → graph, layer on provenance/comments/reviews by hand,
  re-sync (idempotent). `bash examples/gauss/build.sh`
- [`examples/triangular/`](examples/triangular/) — the rest of the schema:
  every `content_type`, a wider `origin` spread, a stale-node demo, a
  `related_to` edge, and the two-axis review shape.
  `bash examples/triangular/build.sh`

The repo's own [`config.yaml`](config.yaml) lists both as one grouped
workspace (`hgraph site`, no `--manifest` needed) — that's what the live demo
is. [`.github/workflows/pages.yml`](.github/workflows/pages.yml) builds and
deploys it on every push to `main`.

## Status

First working slice: storage, full CLI, queries, `sync` from a leanblueprint
`.tex` + Lean sources, and the dashboard/site UI with live and static
review flows. Next: richer authored-field auditing after `sync` (which
nodes/fields have no source-of-truth to sync from).
