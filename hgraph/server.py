"""`hgraph serve` — the dashboard, live, with review/comment write-back.

A tiny stdlib HTTP server: it serves the single-page dashboard (in ``live`` mode,
so the page fetches ``/api/graph``) and accepts ``POST /api/review`` /
``/api/comment`` to attach a review or comment to a node — written straight into
the graph files, exactly like ``hgraph add review`` would.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .dashboard import (_KATEX_CDN, _resolve_blueprint, _vendor_katex,
                        build_document, collect, collect_one, discover_bib,
                        discover_titleauthor, render_page, resolve_macros)
from .graph import Graph
from .katex_check import check_katex
from .layout import render_svgs


def serve(g: Graph, *, host: str = "127.0.0.1", port: int = 8000,
          title: str = "Blueprint", macros_from=None, self_contained: bool = False,
          blueprint=None, root: str = ".", validate_katex: bool = True):
    bp = _resolve_blueprint(blueprint, root)
    macros = resolve_macros(bp, macros_from)

    def graph_json() -> bytes:
        data = build_document(g, bp, title=title) if bp else collect(g, title=title)
        data["bib"] = discover_bib(bp) if bp else []
        ta = discover_titleauthor(bp) if bp else {}
        data["docTitle"] = ta.get("title") or title
        data["docAuthor"] = ta.get("author")
        return json.dumps(data, ensure_ascii=False).encode("utf-8")
    katex = _KATEX_CDN
    if self_contained:
        try:
            katex = _vendor_katex()
        except Exception as e:
            print(f"  note: could not vendor KaTeX ({e}); using the CDN")
    startup_data = build_document(g, bp, title=title) if bp else collect(g, title=title)
    # every math span, checked against real KaTeX — surfaced now, not discovered
    # as a blank render in the browser later (empty if Node/katex isn't installed)
    if validate_katex:
        for w in check_katex(startup_data.get("chapters", []), macros):
            print(f"  warning: {w}", file=sys.stderr)
    # precompute the graph layout once at startup (empty if `dot` isn't installed)
    gvsvg = render_svgs(startup_data)
    page = render_page(title=title, katex_head=katex, macros=macros,
                       data=None, live=True, gvsvg=gvsvg).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):        # keep the console quiet
            pass

        def _send(self, code: int, body: bytes, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0].split("#")[0]
            if path in ("/", "/index.html"):
                return self._send(200, page, "text/html; charset=utf-8")
            if path == "/api/graph":
                return self._send(200, graph_json())
            self._send(404, b'{"error":"not found"}')

        def do_POST(self):
            path = self.path.split("?")[0]
            kind = {"/api/review": "review", "/api/comment": "comment"}.get(path)
            if not kind:
                return self._send(404, b'{"error":"not found"}')
            try:
                n = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(n) or b"{}")
                target = data.get("target")
                if not target or not g.has_node(target):
                    raise ValueError("unknown target node")
                content = (data.get("content") or "").strip()
                if not content:
                    raise ValueError("empty content")
                meta = {k: data[k] for k in ("title", "verdict")
                        if data.get(k) not in (None, "")}
                g.add_attachment(target, kind, content,
                                 author=(data.get("author") or None), **meta)
                item = collect_one(g, target)[kind + "s"][-1]
                self._send(200, json.dumps({"ok": True, "item": item}).encode("utf-8"))
            except Exception as e:
                self._send(400, json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"serving “{title}” on http://{host}:{port}   (Ctrl-C to stop)")
    print("  reviews & comments you add in the browser are written into the graph.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
