"""`hgraph` command-line interface.

    hgraph add node   --title "théorème central limite" --type tex --origin book
    hgraph add edge   theoreme-central-limite clt-lean --type formalizes
    hgraph add comment clt-lean --content "tried simp, failed because ..."
    hgraph get        clt-lean
    hgraph modify node clt-lean --set status=proved
    hgraph delete node clt-lean
    hgraph list --type lean
    hgraph ancestors clt-lean --names
    hgraph view union            # or: tex | lean   (add --dot for Graphviz)

Most commands run against ``./hgraph`` by default; ``sync``, ``site``, and
``serve`` also discover a workspace manifest at ``./config.yaml``. Override
the project directory with ``--root <project-dir>``.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

import yaml

from .analysis import Analysis
from .graph import Graph, HGraphError
from .render import (edge_json, get_json, node_json, render_get, stats_json,
                     view_dot, view_text)


def _kv(pairs, reserved=()) -> dict:
    """Parse repeated ``key=value`` options; values are YAML scalars. Keys in
    ``reserved`` have a dedicated flag and would collide with it, so reject them
    with a clear message instead of crashing on a duplicate keyword argument."""
    out = {}
    for p in pairs or ():
        if "=" not in p:
            raise SystemExit(f"--set expects key=value, got '{p}'")
        k, v = p.split("=", 1)
        if k in reserved:
            raise SystemExit(f"--set {k}=… collides with the dedicated --{k} flag; "
                             f"use --{k} instead")
        out[k] = yaml.safe_load(v)
    return out


def _scalar(v):
    """Parse a CLI value as a YAML scalar (so ``0.8`` → float, ``high`` → str)."""
    return yaml.safe_load(v) if v is not None else None


def _content(args) -> str | None:
    if getattr(args, "content_file", None):
        if args.content_file == "-":
            return sys.stdin.read()
        return Path(args.content_file).read_text(encoding="utf-8")
    return getattr(args, "content", None)


def _emit_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _limited(items: list, args) -> tuple[list, int]:
    """Apply ``--limit N`` to a result list; return (shown, total)."""
    total = len(items)
    n = getattr(args, "limit", None)
    return (items[:n] if n is not None else items), total


def _filter_nodes(g: Graph, args) -> list:
    """The queryable node list behind ``hgraph list`` — every filter is ANDed,
    then sorted by ``--sort``."""
    def tags_of(n):
        t = n.meta.get("tags") or []
        return [t] if isinstance(t, str) else list(t)

    out = []
    for n in g.nodes(type=args.type):
        if args.status and n.meta.get("status") != args.status:
            continue
        if args.lean_status and n.meta.get("lean_status") != args.lean_status:
            continue
        if args.tag and args.tag not in tags_of(n):
            continue
        if args.stale and not n.meta.get("stale"):
            continue
        if args.generated:
            gen = n.meta.get("generated")
            if (args.generated == "manual" and gen) or \
               (args.generated != "manual" and gen != args.generated):
                continue
        if args.match and args.match.lower() not in \
                ((n.title or "") + "\n" + n.content).lower():
            continue
        out.append(n)
    keyf = {
        "id": lambda n: n.id,
        "title": lambda n: (n.title or "").lower(),
        "type": lambda n: (n.type or "", n.id),
        "chapter": lambda n: (str(n.meta.get("chapter") or "~"), n.meta.get("order")
                              if isinstance(n.meta.get("order"), int) else 0),
        "order": lambda n: n.meta.get("order") if isinstance(n.meta.get("order"), int) else 1 << 30,
    }[args.sort]
    out.sort(key=keyf)
    return out


def _count(value: int, singular: str, plural: str | None = None) -> str:
    return f"{value:,} {singular if value == 1 else (plural or singular + 's')}"


def _sync_line(result: dict) -> str:
    """Compact result shared by solo and workspace sync output."""
    parts = [
        _count(result["blueprint"], "blueprint node"),
        _count(result["lean"], "Lean declaration"),
        _count(result["edges"], "generated edge"),
    ]
    if result["stale"]:
        parts.append(_count(result["stale"], "node marked stale", "nodes marked stale"))
    return " | ".join(parts)


class _SyncStyle:
    """Small ANSI formatter with an opt-out for redirected/CI output."""

    _codes = {"green": "32", "yellow": "33", "red": "31", "bold": "1"}

    def __init__(self, mode: str = "auto", stream=None):
        stream = stream or sys.stdout
        is_tty = bool(getattr(stream, "isatty", lambda: False)())
        self.enabled = (mode == "always" or
                        (mode == "auto" and is_tty and
                         "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"))

    def __call__(self, text: str, color: str) -> str:
        if not self.enabled:
            return text
        return f"\033[{self._codes[color]}m{text}\033[0m"

    def green(self, text: str) -> str:
        return self(text, "green")

    def yellow(self, text: str) -> str:
        return self(text, "yellow")

    def red(self, text: str) -> str:
        return self(text, "red")

    def bold(self, text: str) -> str:
        return self(text, "bold")


_WARNING_LABELS = {
    "lean": "Lean references not found in scanned sources",
    "dependency": "blueprint dependencies not found",
    "edge": "generated edge conflicts",
    "other": "other sync warnings",
}


def _warning_kind(warning: str) -> str:
    if r"\lean{" in warning and warning.endswith("not found in Lean sources"):
        return "lean"
    if "has no blueprint node" in warning:
        return "dependency"
    if warning.startswith("edge ") and "authored edge present" in warning:
        return "edge"
    return "other"


def _render_warning_summary(warnings: list[str], *, stream, style: _SyncStyle,
                            indent: str = "  ", verbose: bool = False,
                            lean_count: int | None = None) -> int:
    """Render warning categories without losing the full warning list.

    Sync can legitimately produce hundreds of unresolved references when a
    project has only a blueprint or relies on external libraries. Three sample
    lines per category keep the normal report useful; ``--verbose`` expands it.
    """
    groups: dict[str, list[str]] = {}
    for warning in warnings:
        groups.setdefault(_warning_kind(warning), []).append(warning)
    for kind, rows in groups.items():
        label = _WARNING_LABELS[kind]
        if kind == "lean" and lean_count == 0:
            label += " (no Lean declarations scanned)"
        print(f"{indent}{style.yellow('[warning]')} {len(rows):,} {label}",
              file=stream)
        shown = rows if verbose else rows[:3]
        for warning in shown:
            print(f"{indent}  - {warning}", file=stream)
        if len(rows) > len(shown):
            print(f"{indent}  ... {len(rows) - len(shown):,} more; use --verbose to show all",
                  file=stream)
    return len(warnings)


def _warn_sync_preflight(statuses: list[dict], *, command: str,
                         verbose: bool = False) -> None:
    """Print actionable source/graph inconsistencies found before ``serve``."""
    problem_states = {"out_of_sync", "missing", "empty", "unconfigured", "error"}
    problems = [s for s in statuses if s["state"] in problem_states]
    has_source_warnings = any(s.get("result", {}).get("warnings") for s in statuses)
    if not problems and not has_source_warnings:
        return

    style = _SyncStyle(stream=sys.stderr)
    print(style.yellow("warning: some project data may be incomplete or out of sync:"),
          file=sys.stderr)
    for s in problems:
        marker = style.red("[error]") if s["state"] == "error" else style.yellow("[check]")
        print(f"  {marker} {s['name']} ({s['root']}): {s['message']}", file=sys.stderr)
    for s in statuses:
        warnings = s.get("result", {}).get("warnings", [])
        if not warnings:
            continue
        print(f"  {s['name']} ({s['root']}):", file=sys.stderr)
        _render_warning_summary(
            warnings, stream=sys.stderr, style=style, indent="    ", verbose=verbose,
            lean_count=s.get("result", {}).get("lean"))
    needs_fix = has_source_warnings or any(s["state"] != "out_of_sync" for s in problems)
    action = ("fix the source/configuration errors, then run" if needs_fix else "run")
    print(f"  {action} `{command}` before serving.", file=sys.stderr)


# The most recent serve preflight thread. Serving blocks the main thread, so
# nothing in-process ever needs this — but the tests mock the server away and
# then await this to observe the (now backgrounded) warning output.
_LAST_SERVE_PREFLIGHT = None


def _warn_sync_preflight_async(statuses_fn, *, command: str, verbose: bool = False):
    """Run the ``serve`` staleness check off the critical path.

    The check re-syncs every project in memory to spot on-disk data that has
    drifted from its sources — seconds of work on a large workspace — but it
    only *warns*; serving proceeds regardless. Running it inline meant the
    server did not bind until it finished, so a big workspace felt slow to
    start. In a daemon thread instead, the server comes up immediately and the
    warnings (if any) print a moment later, to the same stderr."""
    import threading

    def run():
        try:
            _warn_sync_preflight(statuses_fn(), command=command, verbose=verbose)
        except Exception:
            pass   # a check that itself blows up must never take the server down

    global _LAST_SERVE_PREFLIGHT
    th = threading.Thread(target=run, daemon=True)
    _LAST_SERVE_PREFLIGHT = th
    th.start()
    return th


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hgraph", description="a plain-files semantic graph")
    p.add_argument("--root", default=".", help="project dir containing hgraph/ (default: .)")
    sub = p.add_subparsers(dest="cmd", required=True)

    # ---- add {node,edge,comment} ----------------------------------------- #
    add = sub.add_parser("add", help="add a node, edge, or comment").add_subparsers(
        dest="what", required=True)

    an = add.add_parser("node", help="add a node")
    an.add_argument("--title", required=True)
    an.add_argument("--type", help="tex, lean, informal, ...")
    an.add_argument("--key", help="human key hashed into the id (default: title); "
                                  "address the node later by key:<key>")
    an.add_argument("--id", help="force a raw id (escape hatch; skips hashing)")
    an.add_argument("--content")
    an.add_argument("--content-file", help="read content from a file (or - for stdin)")
    an.add_argument("--origin")
    an.add_argument("--author", help="who created it (a name, a tool, …)")
    an.add_argument("--content-type", dest="content_type")
    an.add_argument("--set", action="append", metavar="k=v", help="extra metadata")

    ae = add.add_parser("edge", help="add an edge")
    ae.add_argument("source")
    ae.add_argument("target")
    ae.add_argument("--type", required=True, help="uses (hard), formalizes (identity), related_to (associative)")
    g = ae.add_mutually_exclusive_group()
    g.add_argument("--hard", action="store_true", help="force dependency edge")
    g.add_argument("--soft", action="store_true", help="force semantic (non-dep) edge")
    ae.add_argument("--replace", action="store_true",
                    help="overwrite an edge already present on this ordered pair "
                         "(only one edge is kept per pair)")
    ae.add_argument("--set", action="append", metavar="k=v")

    ac = add.add_parser("comment", help="attach a freeform comment to a node")
    ac.add_argument("target")
    ac.add_argument("--content")
    ac.add_argument("--content-file")
    ac.add_argument("--author")
    ac.add_argument("--title", help="short heading for the note")
    ac.add_argument("--set", action="append", metavar="k=v", help="extra metadata")

    ar = add.add_parser("review", help="attach a Maths/Lean good-or-bad review to a node")
    ar.add_argument("target")
    ar.add_argument("--author")
    ar.add_argument("--maths", choices=["good", "bad"], help="is the mathematics right")
    ar.add_argument("--maths-comment", dest="maths_comment")
    ar.add_argument("--lean", choices=["good", "bad"], help="is the Lean formalization right")
    ar.add_argument("--lean-comment", dest="lean_comment")
    ar.add_argument("--set", action="append", metavar="k=v", help="extra metadata")

    # ---- get / modify / delete / list ------------------------------------ #
    gp = sub.add_parser("get", help="render a node (content + links + deps + notes)")
    gp.add_argument("id")
    gp.add_argument("--json", action="store_true", help="emit the full neighbourhood as JSON")

    mo = sub.add_parser("modify", help="modify a node").add_subparsers(
        dest="what", required=True).add_parser("node")
    mo.add_argument("id")
    mo.add_argument("--title")
    mo.add_argument("--type")
    mo.add_argument("--content")
    mo.add_argument("--content-file")
    mo.add_argument("--set", action="append", metavar="k=v")
    mo.add_argument("--unset", action="append", metavar="key", default=[])

    de = sub.add_parser("delete", help="delete a node, edge, comment, or review"
                        ).add_subparsers(dest="what", required=True)
    de.add_parser("node").add_argument("id")
    de.add_parser("edge").add_argument("id", help="the edge id 'source__target' (see `hgraph edges`)")
    for kind in ("comment", "review"):
        dk = de.add_parser(kind, help=f"delete one {kind} attached to a node")
        dk.add_argument("target", help="the node the note is attached to")
        dk.add_argument("--n", type=int, required=True,
                        help=f"which {kind} to delete (its number, shown by `get`)")

    ls = sub.add_parser("list", help="list / query nodes")
    ls.add_argument("--type", help="tex, lean, …")
    ls.add_argument("--status", help="filter by the authored `status` field")
    ls.add_argument("--lean-status", dest="lean_status",
                    help="mathlib_ok | lean_ok | sorry | empty")
    ls.add_argument("--tag", help="only nodes carrying this tag")
    ls.add_argument("--match", help="case-insensitive substring in title or content")
    ls.add_argument("--stale", action="store_true", help="only nodes whose source vanished")
    ls.add_argument("--generated", choices=["blueprint", "lean", "manual"],
                    help="filter by provenance (manual = hand-added)")
    ls.add_argument("--state", choices=["closed", "ready", "blocked",
                                        "formalized_open", "informal"],
                    help="dependency-closure state (see `hgraph frontier`/`stats`)")
    ls.add_argument("--sort", choices=["id", "title", "type", "chapter", "order"],
                    default="id", help="sort key (default: id)")
    ls.add_argument("--limit", type=int, metavar="N", help="show only the first N")
    ls.add_argument("--json", action="store_true", help="emit JSON")

    el = sub.add_parser("edges", help="list / query edges")
    el.add_argument("--source", help="node ref (id or label:/decl:/key:)")
    el.add_argument("--target", help="node ref (id or label:/decl:/key:)")
    el.add_argument("--type")
    elg = el.add_mutually_exclusive_group()
    elg.add_argument("--hard", action="store_true"); elg.add_argument("--soft", action="store_true")
    el.add_argument("--limit", type=int, metavar="N", help="show only the first N")
    el.add_argument("--json", action="store_true", help="emit JSON")

    for name in ("ancestors", "descendants"):
        q = sub.add_parser(name, help=f"transitive {name} over dependency edges")
        q.add_argument("id")
        q.add_argument("--names", action="store_true", help="show titles too")
        q.add_argument("--limit", type=int, metavar="N", help="show only the first N")
        q.add_argument("--json", action="store_true", help="emit JSON")

    stp = sub.add_parser("stats", help="summary counts (types, lean_status, "
                         "closure states, reviews, stale)")
    stp.add_argument("--json", action="store_true", help="emit JSON")

    fr = sub.add_parser("frontier", help="what to work on next: nodes whose "
                        "prerequisites are done, ranked by downstream impact")
    fr.add_argument("--type", help="restrict to a node type (e.g. tex)")
    fr.add_argument("--limit", type=int, metavar="N", help="show only the first N")
    fr.add_argument("--json", action="store_true", help="emit JSON")

    vw = sub.add_parser("view", help="tex | lean | union view")
    vw.add_argument("kind", choices=["tex", "lean", "union"])
    vw.add_argument("--dot", action="store_true", help="emit Graphviz DOT")

    sy = sub.add_parser(
        "sync", help="sync one project, or every project in a workspace manifest")
    sy.add_argument("--blueprint", help="path to the leanblueprint .tex")
    sy.add_argument("--lean", action="append", default=[], metavar="PATH",
                    help="a .lean file or a directory of them (repeatable)")
    sy.add_argument("--manifest", help="sync every project in this workspace manifest; "
                    "default: auto-detect ./config.yaml when no source flags are given")
    sy.add_argument("-v", "--verbose", action="store_true",
                    help="show every source warning (default: three examples per category)")
    sy.add_argument("--color", choices=["auto", "always", "never"], default="auto",
                    help="color status output (default: auto; respects NO_COLOR)")

    review = sub.add_parser(
        "review", help="share local reviews/comments with collaborators through GitHub"
    ).add_subparsers(dest="what", required=True)
    send = review.add_parser(
        "send", help="open one issue containing feedback absent from the GitHub baseline")
    send.add_argument("--repo", help="GitHub owner/name (default: site.repo or current gh repo)")
    send.add_argument("--base", metavar="BRANCH",
                      help="remote branch to compare with (default: repository default branch)")
    send.add_argument("--title", help="override the generated issue title")
    send.add_argument("--label", action="append", default=[], metavar="NAME",
                      help="label to add to the issue (repeatable; label must already exist)")
    kinds = send.add_mutually_exclusive_group()
    kinds.add_argument("--reviews-only", action="store_true",
                       help="send review attachments, excluding freeform comments")
    kinds.add_argument("--comments-only", action="store_true",
                       help="send freeform comments, excluding reviews")
    send.add_argument("--dry-run", action="store_true",
                      help="print the issue and comment bodies without creating anything")

    st = sub.add_parser("site", help="write a landing index.html (multi-project from a "
                        "manifest, or a solo project's own hgraph/config.yaml)")
    st.add_argument("--manifest", help="YAML manifest listing the projects (see "
                    "hgraph.site docstring); default: ./config.yaml, else a solo "
                    "project synthesized from hgraph/config.yaml's site: block")
    st.add_argument("--out", default="_site/index.html",
                    help="output HTML path; the bundle and each project's "
                         "data.json land beside it (default: _site/index.html, "
                         "so generated files never mix into your sources)")
    st.add_argument("--overview", help="a Markdown or HTML fragment to inject as the hero "
                    "(overrides the manifest's/config's `overview:` key)")

    sv = sub.add_parser("serve", help="serve the site live (review/comment write-back); "
                        "a workspace config.yaml serves the whole site, live")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--title", default="Blueprint")
    sv.add_argument("--macros", help="a .sty/.tex preamble to lift KaTeX macros from")
    sv.add_argument("--repo", help="owner/name — shown alongside the live review form "
                    "(default: hgraph/config.yaml's site.repo)")
    sv.add_argument("-v", "--verbose", action="store_true",
                    help="show every sync warning before serving")
    sv.add_argument("--manifest", help="serve a whole workspace (see `hgraph site`) instead "
                    "of one project; default: auto-detect ./config.yaml")

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    g = Graph.open(args.root)

    try:
        if args.cmd == "add" and args.what == "node":
            nid = g.add_node(
                args.title, type=args.type, id=args.id, key=args.key,
                content=_content(args) or "", author=args.author,
                origin=args.origin, content_type=args.content_type,
                **_kv(args.set, {"title", "type", "id", "key", "content",
                                 "author", "origin", "content_type"}))
            print(nid)

        elif args.cmd == "add" and args.what == "edge":
            hard = True if args.hard else (False if args.soft else None)
            print(g.add_edge(g.resolve(args.source), g.resolve(args.target),
                             args.type, hard=hard, replace=args.replace,
                             **_kv(args.set, {"source", "target", "type", "hard"})))

        elif args.cmd == "add" and args.what == "comment":
            c = _content(args)
            if not c:
                raise SystemExit("comment needs --content or --content-file")
            extra = {"title": args.title, **_kv(args.set, {"author", "title"})}
            print(g.add_attachment(g.resolve(args.target), "comment", c,
                                   author=args.author,
                                   **{k: v for k, v in extra.items() if v is not None}))

        elif args.cmd == "add" and args.what == "review":
            if not args.maths and not args.lean:
                raise SystemExit("review needs --maths good|bad and/or --lean good|bad")
            extra = {"maths_verdict": args.maths, "maths_comment": args.maths_comment,
                     "lean_verdict": args.lean, "lean_comment": args.lean_comment,
                     **_kv(args.set, {"author", "maths_verdict", "maths_comment",
                                      "lean_verdict", "lean_comment"})}
            print(g.add_attachment(g.resolve(args.target), "review", "",
                                   author=args.author,
                                   **{k: v for k, v in extra.items() if v is not None}))

        elif args.cmd == "get":
            nid = g.resolve(args.id)
            _emit_json(get_json(g, nid)) if args.json else print(render_get(g, nid))

        elif args.cmd == "modify":
            # same reservation `add node` applies: title/type/content have
            # real flags; letting --set title=x write them through set_meta
            # would silently shadow the node's actual title field
            g.modify_node(g.resolve(args.id), title=args.title, type=args.type,
                          content=_content(args),
                          set_meta=_kv(args.set, {"title", "type", "content", "id"}),
                          unset=args.unset)
            print(f"modified {args.id}")

        elif args.cmd == "delete" and args.what == "node":
            nid = g.resolve(args.id)
            generated = g.get_node(nid).meta.get("generated")
            g.delete_node(nid); print(f"deleted node {args.id}")
            if generated:
                print("  note: this node is derived from source; the next `sync` "
                      "will recreate it (without its comments). Remove it from the "
                      "blueprint/Lean source, or leave it to be marked stale instead.",
                      file=sys.stderr)
        elif args.cmd == "delete" and args.what == "edge":
            g.delete_edge(args.id); print(f"deleted edge {args.id}")
        elif args.cmd == "delete" and args.what in ("comment", "review"):
            g.delete_attachment(g.resolve(args.target), args.what, args.n)
            print(f"deleted {args.what} #{args.n} on {args.target}")

        elif args.cmd == "list":
            picked = _filter_nodes(g, args)
            if args.state:                       # closure state → needs the graph analysis
                a = Analysis(g)
                if args.state == "informal":
                    picked = [n for n in picked
                              if (n.meta.get("lean_status") or "empty") == "empty"]
                else:
                    picked = [n for n in picked if a.states.get(n.id) == args.state]
            nodes, total = _limited(picked, args)
            if args.json:
                _emit_json([node_json(n) for n in nodes])
            else:
                for n in nodes:
                    flags = " (stale)" if n.meta.get("stale") else ""
                    print(f"{n.id}\t[{n.type or '?'}]\t{n.title or ''}{flags}")
                if len(nodes) < total:
                    print(f"… {len(nodes)} of {total} (use --limit to change)",
                          file=sys.stderr)

        elif args.cmd == "edges":
            hard = True if args.hard else (False if args.soft else None)
            src = g.resolve(args.source) if args.source else None
            tgt = g.resolve(args.target) if args.target else None
            found = g.edges(source=src, target=tgt, type=args.type, hard=hard)
            edges, total = _limited(found, args)
            if args.json:
                _emit_json([edge_json(e) for e in edges])
            else:
                for e in edges:
                    kind = "hard" if e.hard else "soft"
                    print(f"{e.id}\t{e.source} --{e.type}({kind})--> {e.target}")
                if len(edges) < total:
                    print(f"… {len(edges)} of {total} (use --limit to change)",
                          file=sys.stderr)

        elif args.cmd in ("ancestors", "descendants"):
            ids, total = _limited(getattr(g, args.cmd)(g.resolve(args.id)), args)
            if args.json:
                _emit_json([{"id": i, "title": g.get_node(i).title} for i in ids]
                           if args.names else ids)
            else:
                for i in ids:
                    print(f"{i}\t{g.get_node(i).title or ''}" if args.names else i)
                if len(ids) < total:
                    print(f"… {len(ids)} of {total} (use --limit to change)",
                          file=sys.stderr)

        elif args.cmd == "stats":
            s = stats_json(g)
            s["closure"] = Analysis(g).state_counts()
            if args.json:
                _emit_json(s)
            else:
                print(f"nodes: {s['nodes']}   edges: {s['edges']} "
                      f"({s['hard_edges']} hard)   reviewed: {s['reviewed']}"
                      + (f"   stale: {s['stale']}" if s['stale'] else ""))
                c = s["closure"]
                print(f"  closure: closed={c['closed']}, ready={c['ready']}, "
                      f"blocked={c['blocked']}, formalized-but-open={c['formalized_open']}, "
                      f"informal={c['informal']}")
                for label, key in (("by type", "by_type"),
                                   ("tex lean_status", "tex_lean_status"),
                                   ("by status", "by_status")):
                    if s[key]:
                        print(f"  {label}: "
                              + ", ".join(f"{k}={v}" for k, v in s[key].items()))

        elif args.cmd == "frontier":
            rows = Analysis(g).frontier()
            if args.type:
                rows = [r for r in rows if r["type"] == args.type]
            rows, total = _limited(rows, args)
            if args.json:
                _emit_json(rows)
            else:
                if not rows:
                    print("frontier empty — nothing is unblocked "
                          "(all remaining work has open prerequisites).")
                for r in rows:
                    kind = f"({r['kind']})" if r['kind'] else ""
                    print(f"  {r['unlocks']:>4} unlocks · {r['direct_uses']:>2} uses  "
                          f"[{r['lean_status']:<10}] {r['title'] or r['id']} {kind}")
                if len(rows) < total:
                    print(f"… {len(rows)} of {total} ready (use --limit to change)",
                          file=sys.stderr)

        elif args.cmd == "view":
            print(view_dot(g, args.kind) if args.dot else view_text(g, args.kind))

        elif args.cmd == "sync":
            from .site import looks_like_manifest
            from .sync import load_config, sync, sync_from_config
            blueprint, lean = args.blueprint, list(args.lean)
            root = Path(args.root)
            auto_manifest = root / "config.yaml"
            manifest_path = Path(args.manifest) if args.manifest else auto_manifest
            workspace = (not blueprint and not lean and
                         (bool(args.manifest) or
                          (auto_manifest.exists() and looks_like_manifest(auto_manifest))))

            if args.manifest and (blueprint or lean):
                print("error: --manifest cannot be combined with --blueprint or --lean",
                      file=sys.stderr)
                return 2

            if workspace:
                if not manifest_path.exists() or not looks_like_manifest(manifest_path):
                    raise HGraphError(f"not an hgraph workspace manifest: {manifest_path}")
                manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
                projects = manifest["projects"]
                failures = 0
                synced = 0
                skipped = 0
                warning_total = 0
                style = _SyncStyle(args.color, sys.stdout)
                print(style.bold(f"Syncing {_count(len(projects), 'workspace project')} "
                                 f"from {manifest_path}"), flush=True)
                for project in projects:
                    name = project.get("name") or str(project["root"])
                    proot = manifest_path.parent / str(project["root"])
                    try:
                        cfg = load_config(proot)
                        if not cfg["blueprint"] and not cfg["lean"]:
                            skipped += 1
                            print(f"  {style.yellow('[skipped]')} {name}: no blueprint/Lean "
                                  f"sources in {proot / 'hgraph/config.yaml'}", flush=True)
                            continue
                        result = sync_from_config(proot)
                    except Exception as e:
                        failures += 1
                        print(f"  {style.red('[failed]')} {name}: {e}", flush=True)
                        continue
                    synced += 1
                    print(f"  {style.green('[synced]')} {name}: {_sync_line(result)}",
                          flush=True)
                    warning_total += _render_warning_summary(
                        result["warnings"], stream=sys.stdout, style=style, indent="    ",
                        verbose=args.verbose, lean_count=result["lean"])
                summary = (f"Workspace sync complete: {synced:,} synced, {skipped:,} skipped, "
                           f"{failures:,} failed, {_count(warning_total, 'warning')}")
                summary_style = style.red if failures else style.yellow if warning_total else style.green
                print(summary_style(summary), flush=True)
                return 1 if failures else 0

            if not blueprint and not lean:          # fall back to project config
                cfg = load_config(args.root)
                blueprint, lean = cfg["blueprint"], cfg["lean"]
            if not blueprint and not lean:
                print("nothing to sync: no --blueprint / --lean given, and no "
                      "hgraph/config.yaml found.\n"
                      "  pass e.g.  hgraph sync --lean Lean --blueprint blueprint/main.tex\n"
                      "  or create  <root>/hgraph/config.yaml  with `blueprint:` / `lean:` keys.",
                      file=sys.stderr)
                return 2
            r = sync(g, blueprint=blueprint, lean_paths=lean, root=args.root)
            style = _SyncStyle(args.color, sys.stdout)
            print(f"{style.green('[synced]')} {_sync_line(r)}")
            _render_warning_summary(r["warnings"], stream=sys.stdout, style=style,
                                    verbose=args.verbose, lean_count=r["lean"])

        elif args.cmd == "review" and args.what == "send":
            from .collaboration import send_review_batch
            kinds = ({"review"} if args.reviews_only else
                     {"comment"} if args.comments_only else
                     {"review", "comment"})
            result = send_review_batch(
                args.root, repo=args.repo, base=args.base, kinds=kinds,
                title=args.title, labels=args.label, dry_run=args.dry_run)
            pending = result["pending"]
            if not pending:
                print(f"No local reviews/comments differ from "
                      f"{result['repo']}@{result['branch']}.")
            elif args.dry_run:
                print(f"Would send {len(pending)} attachment(s) to "
                      f"{result['repo']}@{result['branch']}:\n")
                print(f"ISSUE TITLE\n{result['title']}\n\nISSUE BODY\n{result['body']}")
                for index, comment in enumerate(result["comments"], 1):
                    print(f"\nISSUE COMMENT {index}/{len(pending)}\n{comment}")
            else:
                reviews = sum(a.kind == "review" for a in pending)
                comments = sum(a.kind == "comment" for a in pending)
                print(f"Created {result['issue']}")
                print(f"  posted {_count(reviews, 'review')} and "
                      f"{_count(comments, 'comment')} as separate issue comments")

        elif args.cmd == "site":
            from .site import looks_like_manifest, write_from_manifest, write_solo
            root = Path(args.root)
            workspace = root / "config.yaml"
            out_path = Path(args.out)
            # only auto-adopt ./config.yaml if it really is an hgraph manifest —
            # the name is shared with other tools (see looks_like_manifest)
            auto = workspace.exists() and looks_like_manifest(workspace)
            if args.manifest:
                write_from_manifest(args.manifest, out_path=out_path, overview_path=args.overview)
            elif auto:
                write_from_manifest(workspace, out_path=out_path, overview_path=args.overview)
            else:
                from .sync import load_config
                site_cfg = load_config(args.root).get("site") or {}
                if not site_cfg:
                    why = ("./config.yaml is not an hgraph manifest (no `projects:` list "
                           "of entries with a `root:`)" if workspace.exists() else
                           "no --manifest and no ./config.yaml")
                    print(f"nothing to build a site from: {why}, "
                          "and no site: block in hgraph/config.yaml.\n"
                          "  pass e.g.  hgraph site --manifest workspace.yaml\n"
                          "  or add a `site:` block to <root>/hgraph/config.yaml.",
                          file=sys.stderr)
                    return 2
                write_solo(site_cfg, root=root, out_path=out_path, overview_path=args.overview)
            print(f"wrote {out_path} (+ assets/)")

        elif args.cmd == "serve":
            from .site import looks_like_manifest
            from .sync import load_config, project_sync_status, workspace_sync_status
            root = Path(args.root)
            workspace = Path(args.manifest) if args.manifest else (root / "config.yaml")
            # same rule as `site`: a ./config.yaml belonging to another tool is
            # not a workspace — fall through and serve the solo project
            if args.manifest or (workspace.exists() and looks_like_manifest(workspace)):
                from .server import serve_workspace
                if not workspace.exists() or not looks_like_manifest(workspace):
                    raise HGraphError(f"not an hgraph workspace manifest: {workspace}")
                manifest = yaml.safe_load(workspace.read_text(encoding="utf-8")) or {}
                command = (f"hgraph sync --manifest {shlex.quote(str(workspace))}"
                           if args.manifest
                           else (f"hgraph --root {shlex.quote(str(root))} sync"
                                 if str(root) != "."
                                 else "hgraph sync"))
                _warn_sync_preflight_async(
                    lambda: workspace_sync_status(manifest, workspace.parent),
                    command=command, verbose=args.verbose)
                serve_workspace(manifest, workspace.parent, host=args.host, port=args.port)
            elif not (root / "hgraph").is_dir():
                # Neither a workspace nor a project. `Graph.open` is happy to
                # hand back an empty graph here, which would serve a blank page
                # titled "Blueprint" and leave the user hunting for their
                # projects — say what's wrong instead.
                what = ("./config.yaml is not an hgraph manifest (no `projects:` list of "
                        "entries with a `root:`)" if workspace.exists() and not args.manifest
                        else "no --manifest was given")
                print(f"nothing to serve: {what}, and {root}/ is not an hgraph project "
                      "either (no hgraph/ directory).\n"
                      "  a workspace:  hgraph serve --manifest site.yaml\n"
                      "  one project:  cd <project> && hgraph serve",
                      file=sys.stderr)
                return 2
            else:
                from .server import serve
                command = (f"hgraph --root {shlex.quote(str(root))} sync"
                           if str(root) != "." else "hgraph sync")
                try:
                    project_name = (load_config(args.root).get("site", {}).get("title")
                                    or root.name)
                except Exception:
                    project_name = root.name
                _warn_sync_preflight_async(
                    lambda: [{"name": project_name, "root": str(root),
                              **project_sync_status(root)}],
                    command=command, verbose=args.verbose)
                serve(g, host=args.host, port=args.port, title=args.title,
                      macros_from=args.macros, root=args.root, repo=args.repo)

    except (HGraphError, OSError, yaml.YAMLError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
