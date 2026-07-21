<div align="center">

# hgraph

**A plain-files semantic graph for Lean autoformalization**

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](./pyproject.toml)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](./LICENSE)
![Status](https://img.shields.io/badge/status-beta-orange)

[Live demo](https://axeldlv00.github.io/hgraph/) · [Examples](#examples) · [CLI reference](#cli-reference)

</div>

---

`hgraph` connects informal mathematics, Lean declarations, proofs, sources,
comments, and reviews in a graph that both people and agents can edit. Each
node and edge is a Markdown file with YAML metadata: there is no database or
event log. The files are the graph, and Git provides its history.

`hgraph sync` can generate this graph from a
[leanblueprint](https://github.com/PatrickMassot/leanblueprint) `.tex` file and
Lean sources. The CLI then exposes dependency queries, proof frontiers, and a
web interface for exploring and reviewing one project or an entire workspace.

## Highlights

- **Plain files.** Inspect, edit, diff, and version every node and edge.
- **Blueprint-to-Lean sync.** Import `\label`, `\uses`, `\lean`, and
  `\mathlibok` metadata without overwriting authored fields.
- **Agent-friendly queries.** Find ancestors, descendants, blocked statements,
  and the next ready-to-prove frontier; listing commands support bounded and
  JSON output.
- **Flexible references.** Address nodes by `label:…`, `decl:…`, or `key:…`
  instead of opaque IDs.
- **Live and static sites.** Browse dependencies, Lean code, comments, and
  reviews locally or publish the same interface as a static site.
- **Multi-project workspaces.** Combine several formalization projects under
  one landing page and deployment.

## Quick start

Requires Python 3.9 or newer.

```bash
git clone https://github.com/axeldlv00/hgraph.git
cd hgraph
python -m pip install -e .
```

From a project containing a blueprint and Lean sources:

```bash
hgraph sync --blueprint blueprint/blueprint.tex --lean Lean
hgraph stats
hgraph frontier --type tex --limit 20
hgraph serve --port 8000
```

Open <http://127.0.0.1:8000> to explore the graph. To avoid repeating source
paths, add `hgraph/config.yaml`:

```yaml
blueprint: blueprint/blueprint.tex
lean: [Lean]
```

Then a bare `hgraph sync` is enough. At a workspace root, the same command
auto-detects `config.yaml` and syncs every configured project in the manifest.

> [!IMPORTANT]
> Use the installed `hgraph` command inside a project, not `python -m hgraph`.
> A local `hgraph/` data directory can otherwise shadow the Python package.

## Core model

Each project stores its graph under `hgraph/`:

```text
hgraph/
├── config.yaml
├── nodes/
│   ├── <id>.md
│   └── <id>/
│       ├── comment-1.md
│       └── review-1.md
└── edges/
    └── <source>__<target>.md
```

A node represents an artifact such as an informal statement, Lean declaration,
proof, or source quotation. Comments and Maths/Lean reviews are attachments to
that node. Every ID is a deterministic 12-character hash, but normal CLI use
relies on human-readable references:

```text
label:gauss_sum
decl:Gauss.sum_id
key:alternate-proof
```

Edges have three deliberately small categories:

| Type | Meaning | Scheduling |
| --- | --- | --- |
| `uses` | The source depends on the target | Hard dependency |
| `formalizes` | Two nodes express the same object in different forms | Soft identity |
| `related_to` | Related but distinct artifacts | Soft association |

`sync` owns fields derived from source files, including labels, declaration
names, document order, Lean status, and generated edges. Authored metadata—such
as provenance, tags, workflow status, comments, reviews, and hand-drawn
edges—is preserved across syncs. Removed source items are marked `stale`, never
silently deleted.

### Dependency states

`lean_status` describes a node locally. Graph queries also account for its
entire hard-dependency closure:

| State | Meaning |
| --- | --- |
| `closed` | The node and all prerequisites are formalized |
| `ready` | All prerequisites are closed; this node is not |
| `blocked` | At least one prerequisite remains open |
| `formalized_open` | The node is formalized, but an upstream dependency is not |

## CLI reference

Commands operate on `./hgraph` by default. Pass `--root <project>` to target a
different project. Query and listing commands support `--json`; use
`hgraph <command> -h` for every option.

| Command | Purpose |
| --- | --- |
| `hgraph sync` | Update one project's graph, or every configured project in a workspace |
| `hgraph stats` | Summarize nodes, statuses, provenance, and graph closure |
| `hgraph list` | Filter nodes by type, status, tags, text, source, or state |
| `hgraph get <ref>` | Show a node with its content, links, dependencies, and notes |
| `hgraph frontier` | Rank statements whose prerequisites are complete |
| `hgraph ancestors <ref>` | Traverse transitive prerequisites |
| `hgraph descendants <ref>` | Traverse reverse dependencies |
| `hgraph view tex\|lean\|union` | Render one graph view, optionally as Graphviz DOT |
| `hgraph add …` | Add a node, edge, comment, or review |
| `hgraph review send` | Share local reviews/comments in a structured GitHub issue |
| `hgraph modify node …` | Update authored node metadata |
| `hgraph delete …` | Delete authored graph data |
| `hgraph serve` | Run the live site with review and comment write-back |
| `hgraph site` | Export a self-contained static site under `_site/` |

Typical queries:

```bash
hgraph list --type tex --lean-status sorry --limit 20
hgraph list --tag flagship --sort chapter --json
hgraph list --match "central limit"
hgraph list --stale
hgraph list --state ready
hgraph ancestors label:gauss_sum --names
```

An ambiguous human-readable reference is rejected rather than guessed. Adding
an edge to an occupied source/target pair is also rejected unless `--replace`
is explicit.

## Sharing reviews

`hgraph review send` publishes feedback for collaboration without requiring
the attachment files to be committed first. It compares every local
`review-*.md` and `comment-*.md` with the same path on the GitHub repository's
default branch, using the file's Git blob hash. New and locally modified files
are included; identical upstream files are omitted.

The command requires an authenticated [GitHub CLI](https://cli.github.com/).
The repository comes from `site.repo` in `hgraph/config.yaml`, or from the
current Git remote as understood by `gh`. A batch creates one issue containing
the project and baseline metadata, then one issue comment per attachment with
its target label, declaration type, source metadata, author, timestamp,
verdicts, and text.

```bash
gh auth login
hgraph review send --dry-run
hgraph review send --label review

# Narrow or override the comparison when needed
hgraph review send --reviews-only
hgraph review send --comments-only --repo owner/repository --base main
```

`--dry-run` prints the complete issue and comment templates without writing to
GitHub. Feedback continues to compare as pending until its attachment file is
present on the selected upstream branch, so rerunning the send command before
the feedback is merged can publish it again.

## Sites and workspaces

`hgraph serve` runs the React interface against live graph data, allowing
reviews and comments to be written back to disk. `hgraph site` exports the same
interface as static files; its review form can instead open a prefilled GitHub
issue when the project config includes `repo: owner/name`.

A project can customize its card and overview in `hgraph/config.yaml`:

```yaml
blueprint: blueprint/blueprint.tex
lean: [Lean]
site:
  title: My project
  subtitle: A one-line description
  overview: overview.md
  repo: owner/name
```

To combine projects, place a workspace `config.yaml` beside their directories:

```yaml
title: My workspace
overview: overview.md
projects:
  - name: Project A
    root: a
    category: Examples
    blurb: A one-line description.
```

From that directory, `hgraph sync`, `hgraph serve`, and `hgraph site` discover
the workspace automatically. A workspace sync continues across projects and
reports each result separately. Before serving, `hgraph` checks each configured
project without writing and warns when generated graph data does not match its
sources, with the exact sync command to run.

Sync warnings are grouped by category and show at most three examples by
default, so a project with hundreds of unresolved Lean references does not
bury actual failures. Pass `hgraph sync --verbose` to show every warning.
The same cap applies to the `serve` preflight; use `hgraph serve --verbose` to
expand it there.
Status colors are enabled automatically on terminals; `--color always|never`
overrides detection, and the standard `NO_COLOR` environment variable is
respected.

Use `hgraph sync --manifest <file>` (and the corresponding `--manifest` option
on `serve` or `site`) to select a different manifest. Use `--out <path>` to
change the static output location.

The frontend is prebuilt into the Python package, so installing and using
`hgraph` does not require Node.js. See
[`frontend/README-DEV.md`](frontend/README-DEV.md) when developing the UI.

## Examples

- [`examples/gauss/`](examples/gauss/) demonstrates the complete sync workflow:
  blueprint and Lean sources, authored metadata, comments, reviews, and an
  idempotent re-sync.
- [`examples/triangular/`](examples/triangular/) covers the wider schema,
  including content and provenance types, stale nodes, soft relationships, and
  two-axis reviews.

Run either example's `build.sh`, or run `hgraph site` at the repository root to
build the combined site shown in the [live demo](https://axeldlv00.github.io/hgraph/).

## Status

`hgraph` is beta software. The current release includes plain-file storage,
sync, graph queries, frontier analysis, and live/static review interfaces. The
next focus is richer auditing of authored fields after sync.

## License

Licensed under the [Apache License 2.0](LICENSE).

## Acknowledgments

The node and edge storage format was inspired by
[Astrolabe](https://arxiv.org/abs/2604.10435).
