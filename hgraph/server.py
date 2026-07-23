"""`hgraph serve` — the site, live, with review/comment write-back.

A tiny stdlib HTTP server: it serves the pre-built React frontend
(``hgraph/webui``, see :mod:`hgraph.site`) and the JSON data it fetches —
``GET /api/site`` (the workspace landing data) and ``GET /<root>/data.json``
per project, both recomputed on every request so the live copy never goes
stale — and accepts ``POST /<root>/api/review`` / ``/api/comment`` to attach
a review or comment straight into that project's graph, exactly like
``hgraph add review``/``hgraph add comment`` would.

Two modes, auto-detected by ``hgraph/cli.py`` the same way ``hgraph site``
picks a manifest:

* **one project** (``serve``) — data at ``/data.json``, no mount prefix.
* **a workspace** (``serve_workspace``) — the landing data at ``/api/site``,
  each project's data + API mounted at ``/<root>/``.
"""

from __future__ import annotations

import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .dashboard import _resolve_blueprint, project_data, resolve_extrefs
from .graph import Graph
from .site import (WEBUI_DIR, build_extref_index, build_site_data,
                   render_index_html, _resolve_theme)


def _tree_sig(*paths: Path | str | None) -> tuple:
    """A cheap change signature over files/directory trees: per root, the
    file count and the latest mtime. Stat-only (``os.scandir``), so it costs
    a few ms even on a large project — whereas rebuilding a project's payload
    re-reads every node file, re-parses the blueprint, rglob-scans it for
    macros/bib, and shells out to Graphviz ``dot``. Any write (a synced node,
    a review POSTed from the browser, an edited ``.tex``) changes the
    signature, so the cache below can never serve stale data."""
    sig: list[tuple] = []
    for p in paths:
        if not p:
            continue
        p = Path(p)
        if p.is_file():
            st = p.stat()
            sig.append((str(p), st.st_mtime_ns, st.st_size))
            continue
        if not p.is_dir():
            continue
        count, latest = 0, 0
        stack = [str(p)]
        while stack:
            d = stack.pop()
            try:
                with os.scandir(d) as it:
                    for en in it:
                        count += 1
                        try:
                            if en.is_dir(follow_symlinks=False):
                                stack.append(en.path)
                            else:
                                m = en.stat(follow_symlinks=False).st_mtime_ns
                                if m > latest:
                                    latest = m
                        except OSError:
                            pass
            except OSError:
                pass
        sig.append((str(p), count, latest))
    return tuple(sig)


class _SigCache:
    """Rebuild ``build()`` only when ``sig()`` changes — the live server used
    to recompute the full payload on *every* request, which made each page
    load pay for graph re-reads plus a ``dot`` subprocess. Thread-safe (the
    server is a ``ThreadingHTTPServer``); builds serialise under the lock so
    a burst of first requests doesn't run ``dot`` several times over."""

    def __init__(self, sig, build):
        self._sig_fn, self._build = sig, build
        self._lock = threading.Lock()
        self._sig: tuple | None = None
        self._val: bytes | None = None

    def get(self) -> bytes:
        sig = self._sig_fn()
        with self._lock:
            if self._val is None or sig != self._sig:
                self._val = self._build()
                self._sig = sig
            return self._val


def _project_sig_paths(root: str | Path) -> list:
    """What a project's ``data.json`` is computed from: the graph files (and
    ``config.yaml``) under ``<root>/hgraph``, plus — when a blueprint is
    configured — the blueprint's whole directory tree (macros/bib/title are
    rglob-discovered from it)."""
    paths: list = [Path(root) / "hgraph"]
    bp = _resolve_blueprint(None, str(root))
    if bp:
        paths.append(Path(bp).parent)
    return paths


def _warm(*caches: _SigCache) -> None:
    """Fill the caches in the background so the very first browser hit doesn't
    pay for the initial build (notably the ``dot`` layout)."""

    def run():
        for c in caches:
            try:
                c.get()
            except Exception:
                pass  # a broken project fails on request, with the real error

    threading.Thread(target=run, daemon=True).start()


# content-hashed bundle files can be cached forever; everything else (data,
# index.html) must always revalidate so live edits show up on reload
_IMMUTABLE = "public, max-age=31536000, immutable"
_NO_CACHE = "no-cache"


def _load_webui_assets() -> dict[str, tuple[bytes, str]]:
    """Read the pre-built frontend once at startup: {"/assets/x.js": (bytes,
    mimetype)}, including "/" as an alias for "/index.html"."""
    assets: dict[str, tuple[bytes, str]] = {}
    for f in WEBUI_DIR.rglob("*"):
        if not f.is_file():
            continue
        rel = "/" + str(f.relative_to(WEBUI_DIR))
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        body = f.read_bytes()
        assets[rel] = (body, ctype)
        if f.name == "index.html":
            assets["/"] = (body, ctype)
    return assets


def _apply_index_config(webui: dict[str, tuple[bytes, str]], manifest: dict,
                        base: Path) -> None:
    """Rewrite the served ``index.html`` (and its ``/`` alias) with the
    manifest's tab title + favicon, so a live ``hgraph serve`` tab reads the
    same as a static export. No data script — the live page fetches
    ``/api/site`` instead."""
    idx = render_index_html(manifest, base=base).encode("utf-8")
    for key in ("/", "/index.html"):
        if key in webui:
            webui[key] = (idx, webui[key][1])


def _apply_attachment(g: Graph, kind: str, data: dict) -> dict:
    """Validate + write one ``POST /api/{review,comment}`` body; returns the
    JSON-able item to echo back. Raises ``ValueError`` on bad input."""
    target = data.get("target")
    if not target or not g.has_node(target):
        raise ValueError("unknown target node")
    if kind == "comment":
        content = (data.get("content") or "").strip()
        if not content:
            raise ValueError("empty content")
        meta = {k: data[k] for k in ("title",) if data.get(k) not in (None, "")}
    else:
        meta = {k: data[k] for k in ("maths_verdict", "maths_comment",
                                     "lean_verdict", "lean_comment")
                if data.get(k) not in (None, "")}
        if not meta.get("maths_verdict") and not meta.get("lean_verdict"):
            raise ValueError("review needs a maths and/or lean verdict")
        content = ""
    g.add_attachment(target, kind, content,
                     author=(data.get("author") or None), **meta)
    from .dashboard import collect_one
    return collect_one(g, target)[kind + "s"][-1]


def serve(g: Graph, *, host: str = "127.0.0.1", port: int = 8000,
          title: str = "Blueprint", macros_from=None, root: str = ".", repo=None) -> None:
    from .sync import load_config
    from .site import build_site_data, solo_manifest

    # a solo project still gets a landing page + card (the same manifest the
    # static export synthesizes via write_solo) — just this one project, home +
    # overview + a click into the project view, not skipped straight to content.
    site_cfg = load_config(root).get("site") or {}
    manifest = solo_manifest(site_cfg, title=title, repo=repo)
    solo_theme = _resolve_theme(manifest["projects"][0], manifest, Path(root))
    site_title = manifest["title"]
    webui = _load_webui_assets()
    _apply_index_config(webui, manifest, Path(root))

    sig_paths = _project_sig_paths(root)
    if macros_from:
        sig_paths.append(Path(macros_from))
    overview = manifest.get("overview")
    site_cache = _SigCache(
        lambda: _tree_sig(*sig_paths, (Path(root) / overview) if overview else None),
        lambda: json.dumps(build_site_data(manifest, base=Path(root)),
                           ensure_ascii=False).encode("utf-8"))
    data_cache = _SigCache(
        lambda: _tree_sig(*sig_paths),
        lambda: json.dumps(project_data(g, title=site_title, macros_from=macros_from,
                                        root=root, repo=repo, theme=solo_theme),
                           ensure_ascii=False).encode("utf-8"))
    _warm(data_cache, site_cache)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):        # keep the console quiet
            pass

        def _send(self, code: int, body: bytes, ctype="application/json",
                  cache=_NO_CACHE):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0].split("#")[0]
            if path == "/api/site":
                return self._send(200, site_cache.get())
            if path == "/data.json":
                return self._send(200, data_cache.get())
            if path in webui:
                body, ctype = webui[path]
                return self._send(200, body, ctype,
                                  cache=_IMMUTABLE if path.startswith("/assets/") else _NO_CACHE)
            self._send(404, b'{"error":"not found"}')

        def do_POST(self):
            path = self.path.split("?")[0]
            kind = {"/api/review": "review", "/api/comment": "comment"}.get(path)
            if not kind:
                return self._send(404, b'{"error":"not found"}')
            try:
                n = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(n) or b"{}")
                item = _apply_attachment(g, kind, data)
                self._send(200, json.dumps({"ok": True, "item": item}).encode("utf-8"))
            except Exception as e:
                self._send(400, json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"serving “{site_title}” on http://{host}:{port}   (Ctrl-C to stop)")
    print("  reviews & comments you add in the browser are written into the graph.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


def serve_workspace(manifest: dict, base: Path, *, host: str = "127.0.0.1",
                    port: int = 8000) -> None:
    """Serve an entire workspace live: the `site` landing data at
    ``/api/site`` (recomputed on every request, so progress bars stay
    current), and every project's own data + review/comment API mounted at
    ``/<root>/`` — one process, one port, instead of one `hgraph serve` per
    project."""
    webui = _load_webui_assets()
    _apply_index_config(webui, manifest, base)

    # The cross-project `\citeext` index (handle -> label→number table). Keyed by
    # every project's graph signature, so editing one project refreshes the
    # numbers a sibling's citations resolve to. Built lazily and shared by all
    # per-project payloads below.
    proots = [base / p["root"] for p in manifest.get("projects", [])]
    index_cache = _SigCache(
        lambda: _tree_sig(*(pr / "hgraph" for pr in proots)),
        lambda: build_extref_index(manifest, base))

    def _project_payload(s: dict) -> bytes:
        data = project_data(s["g"], title=s["title"], root=str(s["root"]),
                            repo=s["repo"], theme=s["theme"])
        data["extrefs"] = resolve_extrefs(data.get("chapters"), index_cache.get())
        return json.dumps(data, ensure_ascii=False).encode("utf-8")

    mounted: dict[str, dict] = {}
    for p in manifest.get("projects", []):
        proot = base / p["root"]
        prefix = "/" + str(p["root"]).strip("/") + "/"
        state = {
            "g": Graph.open(str(proot)), "title": p.get("name", p["root"]),
            "repo": p.get("repo") or manifest.get("repo"), "root": proot,
            "theme": _resolve_theme(p, manifest, base),
        }
        state["cache"] = _SigCache(
            (lambda pr=proot: _tree_sig(*_project_sig_paths(pr))),
            (lambda s=state: _project_payload(s)))
        mounted[prefix] = state

    overview = manifest.get("overview")
    site_cache = _SigCache(
        lambda: _tree_sig(*(s["root"] / "hgraph" for s in mounted.values()),
                          (base / overview) if overview else None),
        lambda: json.dumps(build_site_data(manifest, base=base),
                           ensure_ascii=False).encode("utf-8"))
    # landing first: it is the page a visitor sees on arrival, so warming it
    # ahead of the per-project payloads means a first hit during startup waits
    # on one project's worth of work, not all of them.
    _warm(site_cache, *(s["cache"] for s in mounted.values()))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code: int, body: bytes, ctype="application/json",
                  cache=_NO_CACHE):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.end_headers()
            self.wfile.write(body)

        def _mount(self):
            """Match the request path against a mounted project's prefix —
            longest prefix first, so a root that is a prefix of another
            ("a" vs "a/b") can't shadow the nested project; returns
            (state, sub-path within that project) or (None, path)."""
            path = self.path.split("?")[0].split("#")[0]
            for prefix, state in sorted(mounted.items(),
                                        key=lambda kv: -len(kv[0])):
                if path == prefix.rstrip("/") or path.startswith(prefix):
                    return state, path[len(prefix) - 1:] or "/"
            return None, path

        def do_GET(self):
            path = self.path.split("?")[0].split("#")[0]
            if path == "/api/site":
                return self._send(200, site_cache.get())
            if path in webui:
                body, ctype = webui[path]
                return self._send(200, body, ctype,
                                  cache=_IMMUTABLE if path.startswith("/assets/") else _NO_CACHE)
            state, sub = self._mount()
            if state is not None and sub == "/data.json":
                return self._send(200, state["cache"].get())
            self._send(404, b'{"error":"not found"}')

        def do_POST(self):
            state, sub = self._mount()
            kind = {"/api/review": "review", "/api/comment": "comment"}.get(sub)
            if state is None or not kind:
                return self._send(404, b'{"error":"not found"}')
            try:
                n = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(n) or b"{}")
                item = _apply_attachment(state["g"], kind, data)
                self._send(200, json.dumps({"ok": True, "item": item}).encode("utf-8"))
            except Exception as e:
                self._send(400, json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"serving the workspace on http://{host}:{port}   (Ctrl-C to stop)")
    for prefix, state in mounted.items():
        print(f"  {state['title']}: http://{host}:{port}/#{prefix}")
    print("  reviews & comments you add in the browser are written into the graph.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
