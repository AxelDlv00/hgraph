"""Blueprint dashboard — the full blueprint document, enriched with the graph.

Renders the blueprint the way a reader expects: numbered chapters and sections,
the prose, each statement (numbered, tagged) in its own box enriched with the
graph's data — `lean_status`, a reviewed badge, its Lean declaration (with
syntax-highlighted code), its dependency graph, its reviews/comments.

* ``hgraph dashboard --out site.html`` — static export for GitHub Pages.
* ``hgraph serve`` — the same page, live, with review/comment write-back.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.request
from pathlib import Path

from .graph import Graph
from .katex_check import check_katex
from .layout import render_svgs
from .sync import load_config, parse_document, read_blueprint

_KATEX_VER = "0.16.11"
_KBASE = f"https://cdn.jsdelivr.net/npm/katex@{_KATEX_VER}/dist"
_KATEX_CDN = (
    f'<link rel="stylesheet" href="{_KBASE}/katex.min.css">\n'
    f'<script defer src="{_KBASE}/katex.min.js"></script>\n'
    f'<script defer src="{_KBASE}/contrib/auto-render.min.js"></script>'
)


def _vendor_katex() -> str:
    def get(url: str) -> bytes:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.read()

    css = get(f"{_KBASE}/katex.min.css").decode("utf-8")
    for font in sorted(set(re.findall(r"url\(fonts/([\w.\-]+\.woff2)\)", css))):
        b64 = base64.b64encode(get(f"{_KBASE}/fonts/{font}")).decode("ascii")
        css = css.replace(f"url(fonts/{font})", f"url(data:font/woff2;base64,{b64})")
    css = re.sub(r',url\(fonts/[\w.\-]+\.(?:woff|ttf)\) format\("(?:woff|truetype)"\)', "", css)
    js = get(f"{_KBASE}/katex.min.js").decode("utf-8")
    ar = get(f"{_KBASE}/contrib/auto-render.min.js").decode("utf-8")
    guard = lambda s: s.replace("</script", "<\\/script")
    return f"<style>{css}</style>\n<script>{guard(js)}</script>\n<script>{guard(ar)}</script>"


# --------------------------------------------------------------------------- #
# graph → data
# --------------------------------------------------------------------------- #
def _att(a) -> dict:
    return {"author": a.meta.get("author"), "verdict": a.meta.get("verdict"),
            "title": a.meta.get("title"), "text": a.content,
            "created": a.meta.get("created") or a.meta.get("date"),
            "updated": a.meta.get("updated") or a.meta.get("date")}


def _index(g: Graph):
    nodes = {n.id: n for n in g.nodes()}
    formalizes: dict[str, list[str]] = {}
    deps: dict[str, list[tuple[str, str]]] = {}
    for e in g.edges():
        if e.type == "formalizes":
            formalizes.setdefault(e.source, []).append(e.target)
        elif e.hard:
            deps.setdefault(e.source, []).append((e.target, e.type))
    return nodes, formalizes, deps


def _clip(code: str, n: int = 60) -> str:
    lines = code.split("\n")
    return code if len(lines) <= n else "\n".join(lines[:n]) + "\n  -- … (truncated)"


def _entry(n, formalizes, deps, nodes, g) -> dict:
    lean = [{"name": nodes[l].meta.get("decl"), "status": nodes[l].meta.get("lean_status"),
             "file": nodes[l].meta.get("file"), "code": _clip(nodes[l].content)}
            for l in formalizes.get(n.id, []) if l in nodes]
    dep = [{"id": t, "title": nodes[t].title, "label": nodes[t].meta.get("label"), "type": ty}
           for t, ty in deps.get(n.id, []) if t in nodes]
    reviews, comments = g.attachments(n.id, "review"), g.attachments(n.id, "comment")
    return {
        "id": n.id, "label": n.meta.get("label"), "title": n.title,
        "chapter": n.meta.get("chapter"), "kind": n.meta.get("content_type") or "statement",
        # granularity axis (authored/AI wins; _assign_groups_levels fills the rest)
        "group": n.meta.get("group"), "level": n.meta.get("level"),
        "ref": n.meta.get("ref"),      # source-book provenance (\dcref{…})
        "body": re.sub(r"(?<!\\)%.*", "", n.content),
        "lean_status": n.meta.get("lean_status") or "empty",
        "mathlib_name": n.meta.get("mathlib_name"), "status": n.meta.get("status"),
        "tags": n.meta.get("tags"), "lean": lean, "deps": dep,
        "reviewed": bool(reviews),
        "verdict": (reviews[-1].meta.get("verdict") if reviews else None),
        "reviews": [_att(r) for r in reviews], "comments": [_att(c) for c in comments],
    }


_MED_KINDS = {"theorem", "proposition", "lemma"}


def _assign_groups_levels(entries: list) -> None:
    """Attach a ``group`` (cluster id) and ``level`` (``coarse|medium|fine``) to
    every entry, in place. Values authored on the node (or written by a future
    ``hgraph extract`` AI pass) always win; anything missing gets a **heuristic
    stub** so the graph's group-collapse + level filter have something to render.

    The stub is deliberately cheap and self-contained (no deps): ``group`` by
    label-propagation community detection over the hard-dependency graph (falling
    back to chapter when that degenerates), ``level`` by how foundational a node is
    (``coarse`` = the most-depended-on ~12%; ``medium`` = a main-result kind;
    ``fine`` = the rest). It is a placeholder for AI-assigned values, not a claim
    of good clustering. Because it is computed at build time from the synced graph
    (not persisted to node files), it survives ``build.sh``'s wipe-and-resync.
    """
    n = len(entries)
    if not n:
        return
    idx = {e["id"]: i for i, e in enumerate(entries)}
    adj: list[list[int]] = [[] for _ in range(n)]
    usedby = [0] * n
    for i, e in enumerate(entries):
        for d in (e.get("deps") or []):
            j = idx.get(d["id"])
            if j is None or j == i:
                continue
            adj[i].append(j)
            adj[j].append(i)
            usedby[j] += 1                       # e depends on d ⇒ d is used by e

    # ── group: single-level Louvain (modularity local-moving), deterministic. ──
    # More stable than label propagation, whose ΔQ-free updates tend to collapse a
    # dense dep graph into one monster community. The modularity term penalises that
    # (it grows with Σtot), and an adaptive resolution guarantees a usable split.
    deg = [len(a) for a in adj]
    two_m = sum(deg) or 1

    def louvain(gamma: float) -> list[int]:
        comm = list(range(n))
        sigma = deg[:]                                    # Σtot (degree sum) per community
        for _ in range(20):
            moved = False
            for i in range(n):
                if not adj[i]:
                    continue
                ci = comm[i]
                sigma[ci] -= deg[i]
                nw: dict[int, int] = {}
                for j in adj[i]:
                    nw[comm[j]] = nw.get(comm[j], 0) + 1
                best_c = ci
                best_gain = nw.get(ci, 0) - gamma * deg[i] * sigma[ci] / two_m
                for c, wic in nw.items():
                    if c == ci:
                        continue
                    gain = wic - gamma * deg[i] * sigma[c] / two_m
                    if gain > best_gain + 1e-12 or (abs(gain - best_gain) <= 1e-12 and c < best_c):
                        best_gain, best_c = gain, c
                comm[i] = best_c
                sigma[best_c] += deg[i]
                if best_c != ci:
                    moved = True
            if not moved:
                break
        return comm

    def spread(cm: list[int]) -> tuple[float, int]:
        sz: dict[int, int] = {}
        for i in range(n):
            if adj[i]:
                sz[cm[i]] = sz.get(cm[i], 0) + 1
        tot = sum(sz.values())
        return ((max(sz.values()) / tot) if tot else 1.0), len(sz)

    comm = louvain(1.0)
    for gamma in (1.6, 2.6, 4.0):                          # raise resolution if one blob dominates
        frac, k = spread(comm)
        if frac <= 0.4 and k >= 3:
            break
        comm = louvain(gamma)

    # isolated nodes carry no signal ⇒ bucket them by chapter; connected keep community
    gid = ["ch:" + (entries[i].get("chapter") or "·") if not adj[i] else "c%d" % comm[i]
           for i in range(n)]
    # absorb tiny communities into the neighbouring group they touch most
    MIN = 5
    for _ in range(3):
        gsz: dict[str, int] = {}
        for x in gid:
            gsz[x] = gsz.get(x, 0) + 1
        moved = False
        for i in range(n):
            if not adj[i] or gsz.get(gid[i], 0) >= MIN:
                continue
            cnt: dict[str, int] = {}
            for j in adj[i]:
                if gid[j] != gid[i]:
                    cnt[gid[j]] = cnt.get(gid[j], 0) + 1
            if cnt:
                gid[i] = min(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[0]
                moved = True
        if not moved:
            break

    # cap the count so the group overview stays readable: repeatedly fold the
    # smallest community that still touches another community into that neighbour.
    CAP = 30
    for _ in range(n):
        csz: dict[str, int] = {}
        for i in range(n):
            if adj[i]:
                csz[gid[i]] = csz.get(gid[i], 0) + 1
        if len(csz) <= CAP:
            break
        merged = False
        for small, _sz in sorted(csz.items(), key=lambda kv: (kv[1], kv[0])):
            w: dict[str, int] = {}
            for i in range(n):
                if gid[i] != small:
                    continue
                for j in adj[i]:
                    if gid[j] != small:
                        w[gid[j]] = w.get(gid[j], 0) + 1
            if not w:
                continue                           # island: try the next-smallest
            tgt = max(w.items(), key=lambda kv: (kv[1], kv[0]))[0]
            for i in range(n):
                if gid[i] == small:
                    gid[i] = tgt
            merged = True
            break
        if not merged:
            break

    def stub_group(i: int) -> str:
        return gid[i]

    # ── level: coarse = most-depended-on ~12%; medium = main-result kind; else fine
    order = sorted(range(n), key=lambda i: usedby[i], reverse=True)
    coarse = set(order[:max(1, round(n * 0.12))])

    def stub_level(i: int) -> str:
        if i in coarse and usedby[i] > 0:
            return "coarse"
        if (entries[i].get("kind") or "") in _MED_KINDS:
            return "medium"
        return "fine"

    for i, e in enumerate(entries):
        if not e.get("group"):
            e["group"] = stub_group(i)
        if e.get("level") not in ("coarse", "medium", "fine"):
            e["level"] = stub_level(i)


def collect(g: Graph, *, title: str = "Blueprint") -> dict:
    nodes, formalizes, deps = _index(g)
    entries = [_entry(n, formalizes, deps, nodes, g)
               for n in nodes.values() if n.meta.get("generated") == "blueprint"]
    entries.sort(key=lambda e: (e.get("chapter") or "", e["title"]))
    _assign_groups_levels(entries)
    return {"title": title, "entries": entries}


def collect_one(g: Graph, nid: str) -> dict:
    nodes, formalizes, deps = _index(g)
    return _entry(nodes[nid], formalizes, deps, nodes, g)


_ABBR = {"definition": "Def", "lemma": "Lem", "theorem": "Thm", "proposition": "Prop",
         "corollary": "Cor", "remark": "Rmk", "example": "Ex", "conjecture": "Conj",
         "claim": "Claim", "fact": "Fact"}


def build_document(g: Graph, blueprint: str | Path, *, title: str) -> dict:
    """The full blueprint document, numbered, + a by-id map of enriched statements,
    a label→number cross-reference table, and a statement→chapter location map."""
    nodes, formalizes, deps = _index(g)
    entries = {n.meta.get("label"): _entry(n, formalizes, deps, nodes, g)
               for n in nodes.values() if n.meta.get("generated") == "blueprint"}
    chapters = parse_document(read_blueprint(blueprint))
    by_id, refs, loc = {}, {}, {}
    keys = ("lean_status", "mathlib_name", "reviewed", "verdict", "lean", "deps",
            "reviews", "comments", "status", "tags", "ref", "group")
    for ci, ch in enumerate(chapters, 1):
        ch["num"] = str(ci)
        sec = {2: 0, 3: 0, 4: 0}
        cnt = 0
        for b in ch["blocks"]:
            if b["t"] == "head" and b["level"] <= 4:
                lvl = b["level"]
                sec[lvl] += 1
                for d in (3, 4):
                    if d > lvl:
                        sec[d] = 0
                b["num"] = "%d.%s" % (ci, ".".join(str(sec[l]) for l in range(2, lvl + 1)))
            elif b["t"] == "stmt":
                cnt += 1
                b["num"] = f"{ci}.{cnt}"
                b["abbr"] = _ABBR.get(b["content_type"], b["content_type"].title())
                lbl = b.get("label")
                e = entries.get(lbl) if lbl else None
                if e:
                    b["id"] = e["id"]
                    b["enrich"] = {k: e[k] for k in keys}
                    by_id[e["id"]] = e
                    loc[e["id"]] = ci - 1
                # register every \label alias (canonical + legacy book labels) so
                # a \ref{} to any of them resolves, not just the canonical one
                for alias in (b.get("labels") or ([lbl] if lbl else [])):
                    refs[alias] = {"num": b["num"], "id": (e["id"] if e else None), "abbr": b["abbr"]}
    graph_entries = list(by_id.values())
    _assign_groups_levels(graph_entries)
    return {"title": title, "mode": "doc", "chapters": chapters,
            "entries": graph_entries, "refs": refs, "loc": loc}


# --------------------------------------------------------------------------- #
# page assembly
# --------------------------------------------------------------------------- #
def render_page(*, title, katex_head, macros, data, live, gvsvg=None, home=None) -> str:
    home_html = (f'<a class="home" href="{_esc(home)}" title="All projects">&larr; All projects</a>'
                 if home else "")
    return (_PAGE.replace("__TITLE__", _esc(title))
            .replace("__HOME__", home_html)
            .replace("__KATEX_HEAD__", katex_head)
            .replace("/*__MACROS__*/{}", json.dumps(macros, ensure_ascii=False))
            .replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False) if data else "null")
            .replace("/*__GVSVG__*/null", json.dumps(gvsvg, ensure_ascii=False) if gvsvg else "null")
            .replace("/*__LIVE__*/false", "true" if live else "false"))


def _resolve_blueprint(blueprint, root):
    if blueprint and Path(blueprint).exists():
        return blueprint
    bp = load_config(root).get("blueprint")
    return bp if bp and Path(bp).exists() else None


def _macros(macros_from):
    if macros_from and Path(macros_from).exists():
        return extract_macros(Path(macros_from).read_text(encoding="utf-8"))
    return {}


def build_dashboard(g, *, title="Blueprint", macros_from=None, self_contained=False,
                    blueprint=None, root=".", validate_katex=True, home=None) -> str:
    bp = _resolve_blueprint(blueprint, root)
    data = build_document(g, bp, title=title) if bp else \
        {**collect(g, title=title), "mode": "list"}
    data["bib"] = discover_bib(bp) if bp else []
    ta = discover_titleauthor(bp) if bp else {}
    data["docTitle"] = ta.get("title") or title
    data["docAuthor"] = ta.get("author")
    macros = resolve_macros(bp, macros_from)
    if validate_katex:
        for w in check_katex(data.get("chapters", []), macros):
            print(f"  warning: {w}")
    katex = _KATEX_CDN
    if self_contained:
        try:
            katex = _vendor_katex()
        except Exception as e:
            print(f"  note: could not vendor KaTeX ({e}); using the CDN instead")
    gvsvg = render_svgs(data)          # build-time Graphviz layout ({} if `dot` absent)
    if gvsvg:
        print("  graph: precomputed Graphviz layout embedded (instant open, no CDN)")
    else:
        print("  graph: `dot` not found — graph will lay out client-side (install graphviz to precompute)")
    return render_page(title=title, katex_head=katex, macros=macros,
                       data=data, live=False, gvsvg=gvsvg, home=home)


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --------------------------------------------------------------------------- #
# LaTeX macro extraction
# --------------------------------------------------------------------------- #
def _balanced(text: str, start: int):
    depth = 0
    for k in range(start, len(text)):
        if text[k] == "{":
            depth += 1
        elif text[k] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:k]
    return None


def extract_macros(sty_text: str) -> dict:
    macros: dict[str, str] = {}
    for m in re.finditer(r"\\DeclareMathOperator\*?\{\\([A-Za-z]+)\}\{([^}]*)\}", sty_text):
        macros["\\" + m.group(1)] = "\\operatorname{%s}" % m.group(2)
    for m in re.finditer(r"\\(?:new|renew|provide)command\*?\{\\([A-Za-z]+)\}(?:\[\d+\])?", sty_text):
        brace = sty_text.find("{", m.end())
        body = _balanced(sty_text, brace) if brace != -1 else None
        if body is not None and "\\lean" not in body:
            macros.setdefault("\\" + m.group(1), body)
    for m in re.finditer(r"\\def\s*\\([A-Za-z]+)\s*\{", sty_text):
        body = _balanced(sty_text, m.end() - 1)
        if body is not None and "\\lean" not in body:
            macros.setdefault("\\" + m.group(1), body)
    return macros


def discover_macros(blueprint) -> dict:
    """Auto-discover the project's LaTeX macros (\\Spec, \\Pic, …) by scanning the
    blueprint's own directory tree for ``\\newcommand`` / ``\\DeclareMathOperator``
    / ``\\def`` in any ``.sty`` / ``.tex`` — so KaTeX renders them with no config."""
    macros: dict[str, str] = {}
    root = Path(blueprint).parent if blueprint else None
    if not root or not root.exists():
        return macros
    for f in sorted(list(root.rglob("*.sty")) + list(root.rglob("*.tex"))):
        try:
            for k, v in extract_macros(f.read_text(encoding="utf-8")).items():
                macros.setdefault(k, v)
        except Exception:
            pass
    return macros


def parse_bib(text: str) -> list:
    """Very small BibTeX reader — enough to list entries in the dashboard's
    Bibliography view (key, title, author, year, venue, url)."""
    out = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)\n\s*\}", text, re.S):
        typ, key, body = m.group(1).lower(), m.group(2).strip(), m.group(3)
        if typ in ("comment", "string", "preamble"):
            continue
        f = {}
        for fm in re.finditer(r"(\w+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[^,\n]+)", body):
            f[fm.group(1).lower()] = re.sub(r"\s+", " ", fm.group(2).strip().strip('{}"').strip())
        out.append({"key": key, "type": typ, "title": f.get("title"),
                    "author": f.get("author"), "year": f.get("year"),
                    "journal": f.get("journal"), "booktitle": f.get("booktitle"),
                    "publisher": f.get("publisher"), "volume": f.get("volume"),
                    "number": f.get("number"), "pages": f.get("pages"),
                    "url": f.get("url") or (("https://doi.org/" + f["doi"]) if f.get("doi") else None)})
    return out


def discover_titleauthor(blueprint) -> dict:
    """Find the blueprint's ``\\title{…}`` / ``\\author{…}`` (they usually live in
    the print/web entry .tex, not the content file) so the dashboard can show a
    title page. Brace-balanced so nested macros aren't cut off."""
    root = Path(blueprint).parent if blueprint else None
    out: dict = {}
    if not root or not root.exists():
        return out
    for f in sorted(root.rglob("*.tex")):
        if len(out) == 2:
            break
        try:
            t = f.read_text(encoding="utf-8")
        except Exception:
            continue
        for key in ("title", "author"):
            if key in out:
                continue
            m = re.search(r"\\%s\s*\{" % key, t)
            if m:
                body = _balanced(t, t.index("{", m.start()))
                if body:
                    out[key] = re.sub(r"\s+", " ", body).strip()
    return out


def discover_bib(blueprint) -> list:
    """Parse every ``.bib`` in the blueprint's directory tree (deduped by key)."""
    root = Path(blueprint).parent if blueprint else None
    if not root or not root.exists():
        return []
    out, seen = [], set()
    for f in sorted(root.rglob("*.bib")):
        try:
            for e in parse_bib(f.read_text(encoding="utf-8")):
                if e["key"] not in seen:
                    seen.add(e["key"])
                    out.append(e)
        except Exception:
            pass
    return out


def resolve_macros(blueprint, macros_from) -> dict:
    m = discover_macros(blueprint)
    m.update(_macros(macros_from))            # an explicit --macros wins
    return m


_PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
__KATEX_HEAD__
<style>
:root{--bg:#f4f5f7;--panel:#fff;--fg:#1c2024;--muted:#6b7280;--line:#e2e5ea;--soft:#f0f2f5;
 --accent:#4f46e5;--ok:#6d28d9;--lean:#137333;--sorry:#c2410c;--empty:#9aa2ad;--mathlib:#0b5fd0;--bad:#d11a2a;
 --shadow:0 1px 2px rgba(20,25,35,.05),0 4px 14px rgba(20,25,35,.05)}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;font:15px/1.62 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,sans-serif;
 background:var(--bg);color:var(--fg);-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
header{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.9);backdrop-filter:saturate(1.4) blur(8px);
 border-bottom:1px solid var(--line);padding:11px 24px}
.htop{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
h1{font-size:17px;margin:0;font-weight:700;letter-spacing:-.01em}.sub{color:var(--muted);font-size:13px}
.home{font-size:12.5px;color:var(--muted);border:1px solid var(--line);padding:4px 10px;border-radius:8px;background:var(--panel);white-space:nowrap;font-weight:600}
.home:hover{border-color:var(--accent);color:var(--accent)}
.stats{margin-left:auto;display:flex;gap:15px;flex-wrap:wrap;align-items:center}
.stat{font-size:12.5px;color:var(--muted);white-space:nowrap}.stat b{color:var(--fg);font-size:14px}
.bar{height:6px;border-radius:5px;background:var(--soft);overflow:hidden;width:120px;display:inline-block;vertical-align:middle;margin-left:6px}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,var(--mathlib),var(--lean))}
.chip{font-size:12.5px;padding:5px 11px;border-radius:8px;border:1px solid var(--line);background:var(--panel);cursor:pointer;user-select:none}
.chip.on{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 8%,#fff);color:var(--accent);font-weight:600}
.wrap{display:grid;grid-template-columns:274px minmax(0,1fr) 258px;max-width:1660px;margin:0 auto}
@media(max-width:1240px){.wrap{grid-template-columns:274px minmax(0,1fr)}#outline{display:none}}
@media(max-width:920px){.wrap{grid-template-columns:1fr}#navpanel,#outline{display:none}}
#navpanel{position:sticky;top:58px;align-self:start;max-height:calc(100vh - 68px);overflow:auto;padding:14px 10px 40px;border-right:1px solid var(--line)}
.navq{width:100%;padding:7px 12px;border:1px solid var(--line);border-radius:9px;background:var(--panel);font-size:13.5px}
.navchips{display:flex;gap:5px;flex-wrap:wrap;margin:9px 0 4px}.navchips .chip{font-size:11px;padding:3px 8px}
.navlinks{display:flex;flex-direction:column;gap:1px;margin:10px 0 6px;border-top:1px solid var(--line);padding-top:10px}
.navlink{display:flex;align-items:center;gap:9px;color:var(--fg);font-size:13.5px;padding:7px 9px;border-radius:8px;cursor:pointer;font-weight:550}
.navlink:hover{background:var(--soft)}.navlink.on{background:color-mix(in srgb,var(--accent) 10%,#fff);color:var(--accent)}
.navlink .ni{color:var(--muted);width:16px;text-align:center}.navlink.on .ni{color:var(--accent)}
.navsec{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:700;padding:12px 9px 5px;border-top:1px solid var(--line);margin-top:6px}
#toc .tch{display:flex;align-items:center;gap:6px;color:var(--fg);font-size:13px;padding:6px 9px;border-radius:7px;cursor:pointer;line-height:1.4}
#toc .tch:hover{background:var(--soft)}#toc .tch.sel{background:color-mix(in srgb,var(--accent) 10%,#fff);color:var(--accent);font-weight:600}
#toc .tch .n{color:var(--muted);font-variant-numeric:tabular-nums;min-width:20px}#toc .tch .c{margin-left:auto;color:var(--muted)}
#toc .tsec{display:flex;align-items:center;gap:6px;padding:3px 9px 3px 12px;font-size:12px;color:var(--muted);line-height:1.35;cursor:pointer;border-radius:7px}
#toc .tsec.l3{padding-left:24px;font-size:11.5px}
#toc .tsec:hover{background:var(--soft);color:var(--accent)}#toc .tsec .n{min-width:26px}
.tchev{display:inline-flex;align-items:center;justify-content:center;width:12px;font-size:9px;color:var(--muted);cursor:pointer;flex-shrink:0}
.tchev:hover{color:var(--accent)}
.tchev-sp{display:inline-block;width:12px;flex-shrink:0}
.choverview{background:var(--soft);border:1px solid var(--line);border-radius:11px;padding:10px 14px;margin:12px 0 22px}
.choverview>summary{cursor:pointer;font-size:13px;color:var(--muted);list-style:none;user-select:none}
.choverview>summary b{color:var(--fg)}
.choverview>summary::before{content:"▾ ";color:var(--muted)}.choverview:not([open])>summary::before{content:"▸ "}
.co-row{display:flex;align-items:center;gap:12px;padding:4px 4px;border-radius:6px;margin:1px 0}
.co-row:hover{background:var(--panel)}
.co-sec{font-size:13px;color:#374151;cursor:pointer;flex:1;min-width:0}.co-sec.l3{padding-left:18px;font-size:12.5px}
.co-sec:hover{color:var(--accent)}.co-sec .n{color:var(--muted);font-variant-numeric:tabular-nums;margin-right:7px}
.co-rowmap{display:flex;flex-wrap:wrap;gap:2px;justify-content:flex-end;max-width:55%}
/* right outline — the current chapter's statements, with status, for quick jumps */
#outline{position:sticky;top:58px;align-self:start;max-height:calc(100vh - 68px);overflow:auto;padding:14px 6px 40px;border-left:1px solid var(--line)}
.olh{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:700;padding:2px 8px 9px;display:flex;align-items:center;gap:8px;position:sticky;top:0;background:var(--bg);z-index:1}
.olc{margin-left:auto;background:var(--soft);color:var(--muted);border-radius:20px;padding:1px 8px;font-weight:600}
.olist{display:flex;flex-direction:column;gap:6px}
.oli{display:flex;align-items:center;gap:7px;padding:5px 8px;border-radius:7px;cursor:pointer;line-height:1.35;border-left:2px solid transparent}
.oli:hover{background:var(--soft)}
.oli.cur{background:color-mix(in srgb,var(--accent) 9%,#fff);border-left-color:var(--accent)}
.odot{width:8px;height:8px;border-radius:50%;flex:none}.odot.rev{box-shadow:0 0 0 1.5px var(--ok);outline-offset:0}
.onum{font-size:11px;font-weight:700;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap;flex:none}
.oli.cur .onum{color:var(--accent)}
.otitle{font-size:12px;color:#374151;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0}
.oli.cur .otitle{color:var(--fg)}
.olsec{font-size:11px;color:var(--muted);font-weight:600;padding:11px 8px 3px}
.oempty{font-size:12.5px;color:var(--muted);padding:8px}
main{padding:10px 40px 90px;min-width:0;max-width:880px}
.doc h2.ch{font-size:25px;font-weight:750;letter-spacing:-.02em;margin:16px 0 6px}
.doc h3{font-size:19px;margin:30px 0 8px;font-weight:660}.doc h4{font-size:15.5px;margin:22px 0 6px;color:#374151;font-weight:680}
.hn{color:var(--muted);font-weight:600;margin-right:.4em;font-variant-numeric:tabular-nums}
.prose{margin:12px 0;text-align:justify}.prose p{margin:.6em 0}.prose ul,.prose ol{margin:.5em 0;padding-left:1.5em}.prose li{margin:.2em 0}
li.li-lbl{list-style:none;margin-left:-1.15em}.li-mark{font-weight:600;margin-right:.4em}
.env-lbl{font-style:italic;font-weight:600;color:var(--muted);margin-right:.3em}
blockquote{margin:.6em 0;padding-left:.9em;border-left:3px solid var(--line);color:var(--fg)}
.stmt{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--empty);border-radius:11px;
 padding:13px 16px;margin:15px 0;box-shadow:var(--shadow)}
.stmt.k-definition{border-left-color:#0b5fd0}.stmt.k-theorem{border-left-color:#7c3aed}.stmt.k-lemma{border-left-color:#0d9488}.stmt.k-proposition{border-left-color:#b45309}.stmt.k-corollary{border-left-color:#db2777}.stmt.k-remark{border-left-color:#6b7280}.stmt.k-example{border-left-color:#0891b2}.stmt.k-conjecture{border-left-color:#9333ea}
.stmt.flash{animation:flash 1.7s ease}@keyframes flash{0%,20%{background:#fff6d6}100%{background:var(--panel)}}
.sh{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline}
.tag{font-size:12.5px;font-weight:700;padding:1px 8px;border-radius:6px;background:var(--soft);color:#111827;cursor:pointer;white-space:nowrap}
.tag.k-definition{background:#e2f0ff;color:#0b5fd0}.tag.k-theorem{background:#f1e9ff;color:#7c3aed}.tag.k-lemma{background:#d5f3ee;color:#0d9488}.tag.k-proposition{background:#fdeede;color:#b45309}.tag.k-corollary{background:#fde7f1;color:#db2777}.tag.k-remark{background:#eef0f3;color:#6b7280}.tag.k-example{background:#dcf5fb;color:#0891b2}.tag.k-conjecture{background:#f3e8ff;color:#9333ea}
.sw{display:inline-block;width:11px;height:11px;border-radius:3px;vertical-align:middle;margin-right:3px}
.mmrow{margin:9px 0}.mmch{display:block;font-size:12.5px;color:var(--fg);cursor:pointer;margin-bottom:4px}.mmch:hover{color:var(--accent)}
.mmcells{display:flex;flex-wrap:wrap;gap:3px}.mm{width:14px;height:14px;border-radius:3px;cursor:pointer;position:relative;display:flex;align-items:center;justify-content:center}
.st{font-style:italic;color:#374151}
.badges{margin-left:auto;display:flex;gap:5px;flex-wrap:wrap}
.b{font-size:11px;padding:2px 8px;border-radius:7px;font-weight:600;white-space:nowrap}
.b-lean_ok{background:#dcfce7;color:#137333}.b-mathlib_ok{background:#e2f0ff;color:#0b5fd0}
.b-sorry{background:#ffe2e2;color:#d11a2a}.b-empty{background:#eef0f3;color:#6b7280}
.reftag{font-size:11px;padding:2px 8px;border-radius:7px;font-weight:600;background:var(--soft);color:var(--muted);white-space:nowrap;font-variant-numeric:tabular-nums}
.grptag{font-size:11px;padding:2px 8px;border-radius:7px;font-weight:600;background:#eef1ff;color:#4f46e5;white-space:nowrap}
.sbody{margin:9px 0 2px;text-align:justify}
.smeta{font-size:12.5px;color:var(--muted);margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.mtag{font-size:11.5px;padding:2px 9px;border-radius:7px;background:var(--soft);color:var(--muted);white-space:nowrap;border:1px solid transparent;font-variant-numeric:tabular-nums}
.mtag.pop{cursor:pointer}.mtag.pop:hover{border-color:var(--accent);color:var(--fg)}
.mtag.lean{background:#dcfce7;color:#137333}.mtag.mathlib{background:#e2f0ff;color:#0b5fd0}
.mtag.det{cursor:pointer;color:var(--accent);background:color-mix(in srgb,var(--accent) 8%,#fff);font-weight:650;margin-left:auto}
.mtag.det:hover{background:color-mix(in srgb,var(--accent) 15%,#fff)}
/* miniature blueprint cards in the right outline */
.omini{display:block;border:1px solid var(--line);border-left:3px solid var(--empty);border-radius:8px;padding:6px 9px 7px;cursor:pointer;background:var(--panel)}
.omini:hover{border-color:var(--accent)}
.omini.cur{box-shadow:0 0 0 2px color-mix(in srgb,var(--accent) 30%,#fff)}
.omini.k-definition{border-left-color:#0b5fd0}.omini.k-theorem{border-left-color:#7c3aed}.omini.k-lemma{border-left-color:#0d9488}.omini.k-proposition{border-left-color:#b45309}.omini.k-corollary{border-left-color:#db2777}.omini.k-remark{border-left-color:#6b7280}.omini.k-example{border-left-color:#0891b2}.omini.k-conjecture{border-left-color:#9333ea}
.omini-h{display:flex;align-items:center;gap:5px}
.omini .tag{font-size:10px;padding:0 6px}
.omini-b{margin-left:auto;display:flex;gap:3px;align-items:center}.omini-b .b{font-size:9px;padding:1px 5px}
.omini .otitle2{font-size:11.5px;line-height:1.35;color:#374151;margin-top:4px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.ref{color:var(--accent);font-weight:550;cursor:pointer;white-space:nowrap}.ref:hover{text-decoration:underline}
.xref{color:var(--muted)}.leanref{cursor:help}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.86em;background:var(--soft);padding:1px 5px;border-radius:5px}
details.proof{margin:6px 0 16px}details.proof>summary{cursor:pointer;color:var(--muted);font-style:italic;font-size:14px;list-style:none;user-select:none}
details.proof>summary::before{content:"▸ ";font-style:normal}details.proof[open]>summary::before{content:"▾ "}
details.proof .pbody{border-left:2px solid var(--line);padding:2px 0 2px 15px;margin:9px 0;text-align:justify}
pre.lean{background:#f8f9fb;border:1px solid var(--line);border-radius:8px;padding:10px 12px;overflow-x:auto;
 font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;line-height:1.55;margin:4px 0}
.c-kw{color:#8250df;font-weight:600}.c-cm{color:#6b7280;font-style:italic}.c-str{color:#0a5f2c}.c-ty{color:#0b5fd0}
#pv{position:fixed;z-index:60;max-width:480px;max-height:72vh;overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:11px;
 box-shadow:0 10px 34px rgba(20,25,35,.2);padding:12px 14px;font-size:13.5px;display:none;pointer-events:auto}
#pv pre.lean{white-space:pre-wrap;word-break:break-word}
#pv.pv-graph{width:min(760px,94vw);max-width:94vw}   /* explicit width so the local-dependency graph (width:100%) has room to be readable */
#pv .pk{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:700}
#pv .pt{font-weight:640;font-style:italic;margin:2px 0 5px}
#scrim{position:fixed;inset:0;background:rgba(20,25,35,.3);z-index:70;display:none}
#drawer{position:fixed;top:0;right:0;height:100%;width:min(580px,95vw);background:var(--panel);z-index:80;
 box-shadow:-8px 0 34px rgba(20,25,35,.18);transform:translateX(100%);transition:transform .18s ease;overflow:auto}
#drawer.open{transform:none}
.dh{position:sticky;top:0;background:var(--panel);border-bottom:1px solid var(--line);padding:14px 18px;display:flex;gap:10px;align-items:flex-start}
.dh .x{margin-left:auto;border:none;background:var(--soft);width:28px;height:28px;border-radius:7px;cursor:pointer;font-size:16px;color:var(--muted)}
.dc{padding:16px 18px 70px}.dc h3{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:20px 0 8px}
.maketitle{text-align:center;padding:22px 0 20px;border-bottom:1px solid var(--line);margin-bottom:20px}
.maketitle h1{font-size:30px;font-weight:750;letter-spacing:-.02em;margin:0 0 9px;line-height:1.22}
.mkauthor{font-size:15px;color:var(--muted)}
.ovleg-wrap{margin-bottom:6px}
.ov-ch{margin:0 0 10px}
/* chapter: a border-only box (no white-card-on-grey fill) that blends with the
   page; sections/subsections nest inside as plain indented rows, not repeated
   boxes, so the hierarchy reads from structure rather than a stack of cards. */
.ov-chapter{border:1px solid var(--line);border-radius:10px;margin:0 0 8px;transition:border-color .12s}
.ov-chapter:hover{border-color:color-mix(in srgb,var(--accent) 25%,var(--line))}
.ov-chapter>summary{display:flex;align-items:center;flex-wrap:wrap;gap:4px 12px;padding:11px 16px;cursor:pointer;list-style:none;user-select:none}
.ov-chapter>summary::-webkit-details-marker{display:none}
.ov-chapter>summary::before{content:"▸";color:var(--muted);font-size:12px;width:10px}
.ov-chapter[open]>summary::before{content:"▾"}
.ov-chapter>summary:hover .ov-chh{color:var(--accent)}
.ov-sections{padding:2px 16px 12px 34px;display:flex;flex-direction:column;gap:1px}
.ov-chh{font-size:15.5px;font-weight:650;color:var(--fg);cursor:pointer;letter-spacing:-.01em;flex:0 0 auto;max-width:100%}
/* the squares — same look everywhere; .ov-flat is the "all statements at this
   level, un-partitioned" row, hidden once its <details> opens (see below) so
   the finer-grained rows underneath take over instead of piling up alongside */
.mmcells.ov-statements{padding:0}
.ov-chapter>summary .ov-flat,.ov-section>summary .ov-flat{width:100%;margin-top:2px}
.ov-chapter[open]>summary .ov-flat,.ov-section[open]>summary .ov-flat{display:none}
.ov-section{margin:0}
.ov-section>summary{display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px;padding:5px 8px;cursor:pointer;list-style:none;user-select:none;border-radius:6px}
.ov-section>summary::-webkit-details-marker{display:none}
.ov-section>summary::before{content:"▸";color:var(--muted);font-size:10px;width:9px}
.ov-section[open]>summary::before{content:"▾"}
.ov-section>summary:hover,.ov-section-h:hover{background:var(--soft)}
.ov-section-h{display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px;border-radius:6px;padding:5px 8px 5px 17px}
.ov-subsections{padding:2px 0 4px 24px;display:flex;flex-direction:column;gap:1px}
.ov-subsection{display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px;padding:4px 8px 4px 17px;border-radius:6px}
.ov-subsection:hover{background:var(--soft)}
/* .co-sec's flex:1 (sized for its sidebar-TOC usage, alone in its row) would
   otherwise stretch to fill the row and shove these squares far to the right —
   the exact bug fixed elsewhere; here it sits next to squares, so don't grow. */
.ov-section>summary .co-sec,.ov-section-h .co-sec,.ov-subsection .co-sec{flex:0 1 auto;min-width:0}
.ovleg{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;margin:14px 0 18px;align-items:center}
.ovleg span{display:inline-flex;align-items:center;gap:6px}
.ovleg .sw{width:12px;height:12px;border-radius:3px}
.gwrap{overflow-x:auto;border:1px solid var(--line);border-radius:9px;background:var(--bg)}
.graph{display:block}.gn{cursor:pointer}.gn text{font-size:11px}
.ro{font-size:12.5px;color:var(--muted);background:var(--soft);border-radius:8px;padding:9px 12px}
.results .stmt{cursor:pointer}.results .stmt:hover{border-color:var(--accent)}
/* summary + bibliography views */
.sumgrid{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0 24px}
.sumcard{flex:1;min-width:104px;background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:12px 14px;box-shadow:var(--shadow)}
.sumcard .v{font-size:24px;font-weight:750;letter-spacing:-.02em}.sumcard .l{font-size:12.5px;font-weight:600;margin-top:2px}
.sumcard .s{font-size:11px;color:var(--muted);margin-top:4px;line-height:1.4}
.sumsec{font-size:15px;font-weight:700;margin:28px 0 6px;letter-spacing:-.01em}
.ritem{padding:9px 2px;border-bottom:1px solid var(--line)}
.ritem a{color:var(--fg);font-weight:600;cursor:pointer}.ritem a:hover{color:var(--accent)}
.ritem .k{color:var(--muted);font-size:12px;margin-left:6px}
.rmeta{font-size:12px;color:var(--muted);margin-top:3px;display:flex;gap:7px;flex-wrap:wrap;align-items:center}
.rmeta .p{background:var(--soft);border-radius:6px;padding:1px 7px}.rmeta .p b{color:var(--fg);font-weight:650}
.morebtn{margin:12px 0;font-size:12.5px;color:var(--accent);cursor:pointer;font-weight:600}.morebtn:hover{text-decoration:underline}
.stmt.sum{margin:8px 0;padding:10px 14px;cursor:pointer;box-shadow:none}
.stmt.sum:hover{border-color:var(--accent)}.stmt.sum .rmeta{margin-top:7px}
.sumtable{width:100%;border-collapse:collapse;font-size:13px}
.sumtable th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:700;padding:7px 8px;border-bottom:1px solid var(--line)}
.sumtable td{padding:9px 8px;border-bottom:1px solid var(--line);vertical-align:middle}
.sumtable td a{color:var(--fg);cursor:pointer}.sumtable td a:hover{color:var(--accent)}
.segbar{display:flex;height:9px;border-radius:5px;overflow:hidden;background:var(--soft);width:150px;flex:none}.segbar>i{display:block;height:100%}
.bibitem{padding:13px 2px;border-bottom:1px solid var(--line)}
.bibitem .bi-t{line-height:1.55}.bibitem .bi-n{color:var(--muted);font-weight:700;font-variant-numeric:tabular-nums;margin-right:2px}
.bibitem .bi-c{font-size:12.5px;color:var(--muted);margin-top:5px}
.cite{color:var(--accent);cursor:pointer;white-space:nowrap}.cite:hover{text-decoration:underline}
/* ---- full dependency graph (modal) ---- */
#graphmodal{position:fixed;inset:0;z-index:50;background:var(--bg);display:none;flex-direction:column}
#graphmodal.open{display:flex}
.gm-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:9px 16px;border-bottom:1px solid var(--line);background:var(--panel)}
.gm-bar h2{font-size:15px;margin:0 6px 0 0;font-weight:700;letter-spacing:-.01em}
.gm-bar .sp{margin-left:auto}
.gm-sel,.gm-bar input.gm-q{padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--panel);font:inherit;font-size:13px}
.gm-bar input.gm-q{min-width:150px}
.gm-chip{font-size:12px;padding:5px 10px;border-radius:8px;border:1px solid var(--line);background:var(--panel);cursor:pointer;user-select:none}
.gm-chip.on{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 8%,#fff);color:var(--accent);font-weight:600}
.gm-btn{font-size:12.5px;padding:6px 11px;border-radius:8px;border:1px solid var(--line);background:var(--panel);cursor:pointer}
.gm-btn:hover{border-color:var(--accent);color:var(--accent)}
.gm-body{display:flex;flex:1;min-height:0}
.gm-wrap{position:relative;flex:1;min-width:0;overflow:hidden}
#gm-side{width:min(470px,40vw);flex:none;border-left:1px solid var(--line);background:var(--panel);overflow-y:auto;overflow-x:hidden;display:flex;flex-direction:column}
/* only open when a declaration node is actually selected — clicking a chapter
   box (expand/collapse) or empty canvas must not pop this open */
#gm-side.empty{width:0;border-left:none}
#gm-side.empty .gp-close{display:none}
.gp-close{position:sticky;top:0;float:right;margin:8px 8px -34px 0;z-index:2;width:28px;height:28px;
 border:1px solid var(--line);border-radius:7px;background:var(--panel);color:var(--muted);font-size:15px;
 line-height:1;cursor:pointer}
.gp-close:hover{border-color:var(--accent);color:var(--accent)}
@media(max-width:860px){#gm-side{display:none}}
.gp-empty{color:var(--muted);font-size:13px;padding:20px 16px}
.gp-h{position:sticky;top:0;z-index:1;background:var(--panel);border-bottom:1px solid var(--line);padding:13px 16px}
.gp-k{font-size:11px;color:var(--muted);font-weight:700}.gp-t{font-weight:660;font-size:15px;margin-top:2px}
.gp-c{padding:13px 16px 60px;min-width:0}.gp-c h3{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:18px 0 7px}
.gp-c .sbody{font-size:13.5px;overflow-wrap:break-word}
#gm-side .katex-display{overflow-x:auto;overflow-y:hidden;max-width:100%;padding:2px 0}
#gm-side .katex{white-space:normal}
#gm-side pre.lean,#gm-side .gwrap{max-width:100%}
#gm-side code{overflow-wrap:break-word;word-break:break-word}
#gcanvas{position:absolute;top:0;left:0;width:100%;height:100%;display:block;cursor:grab;touch-action:none}
#gcanvas.grabbing{cursor:grabbing}
.gm-gviz{position:absolute;inset:0;overflow:hidden;background:var(--bg);touch-action:none;overscroll-behavior:contain}
.gm-gviz svg{width:100%;height:100%;display:block}
.gm-gviz g.node{cursor:pointer}
.gm-gvload{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:13px}
.gm-float{position:absolute;background:rgba(255,255,255,.93);border:1px solid var(--line);border-radius:10px;box-shadow:var(--shadow);font-size:12px}
.gm-legend{left:14px;bottom:14px;padding:11px 13px;display:flex;flex-direction:column;gap:4px;max-height:calc(100vh - 160px);overflow:auto}
.gm-legend .lg{display:flex;align-items:center;gap:8px;color:var(--fg);font-size:11.5px}
.gm-legend .lgttl{font-size:12px;color:var(--fg);font-weight:700;margin-bottom:4px;max-width:230px;line-height:1.3;cursor:pointer;user-select:none}
.gm-legend .lgcar{float:right;color:var(--muted);transition:transform .15s}
.gm-legend .lgsub{font-weight:400;color:var(--muted);font-size:11px}
.gm-legend.collapsed{max-height:none}
.gm-legend.collapsed>*:not(.lgttl){display:none}
.gm-legend.collapsed .lgsub{display:none}
.gm-legend.collapsed .lgcar{transform:rotate(-90deg)}
.gm-legend .lgsec{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:700;margin:7px 0 2px}
.gm-legend .lgshape{width:15px;height:12px;background:#fff;border:2px solid #607d8b;flex:none}.gm-legend .lgshape.rect{border-radius:3px}.gm-legend .lgshape.ell{border-radius:50%}
.gm-legend .lgb{width:13px;height:11px;background:#fff;border:2.5px solid;border-radius:3px;flex:none}
.gm-legend .lgf{width:13px;height:11px;border:1px solid var(--line);border-radius:3px;flex:none}
.gm-legend .lge{width:20px;height:0;border-top:2px solid #6e7887;flex:none}.gm-legend .lge.dash{border-top-style:dashed}
.gm-hint{right:14px;bottom:14px;padding:7px 11px;color:var(--muted);pointer-events:none}
.gm-count{left:14px;top:14px;padding:6px 11px;color:var(--muted);pointer-events:none}
.gm-count b{color:var(--fg)}
.katex{font-size:1.02em}
</style></head><body>
<header>
  <div class="htop">__HOME__<h1>__TITLE__</h1><span class="sub">blueprint</span><div class="stats" id="stats"></div></div>
</header>
<div class="wrap">
<nav id="navpanel">
  <input type="search" id="q" class="navq" placeholder="search statements…">
  <div class="navchips">
    <span class="chip" data-f="lean_ok">lean ok</span><span class="chip" data-f="mathlib_ok">mathlib</span>
    <span class="chip" data-f="sorry">sorry</span><span class="chip" data-f="empty">no lean</span>
  </div>
  <div class="navlinks">
    <a class="navlink" id="ovbtn"><span class="ni">▤</span>Overview</a>
    <a class="navlink" id="sumbtn"><span class="ni">▣</span>Blueprint summary</a>
    <a class="navlink" id="bibbtn"><span class="ni">❞</span>Blueprint bibliography</a>
    <a class="navlink" id="graphbtn"><span class="ni">◆</span>Dependency graph</a>
  </div>
  <div class="navsec">Chapters</div>
  <div id="toc"></div>
</nav>
<main id="main" class="doc"></main><aside id="outline"></aside></div>
<div id="pv"></div>
<div id="graphmodal">
  <div class="gm-bar">
    <h2>Dependency graph</h2>
    <select class="gm-sel" id="gmChapter" title="Jump to a chapter — expands it without touching any other"><option value="">Open a chapter…</option></select>
    <select class="gm-sel" id="gmLevel" title="Level of detail within expanded chapters (coarse = the most-depended-on statements only)">
      <option value="2">Detail · all</option>
      <option value="1">Detail · coarse + medium</option>
      <option value="0">Detail · coarse only</option>
    </select>
    <button class="gm-btn" id="gmLegend">Legend</button>
    <input type="search" class="gm-q" id="gmQ" placeholder="highlight…">
    <span class="gm-chip" data-gf="mathlib_ok">mathlib</span><span class="gm-chip" data-gf="lean_ok">lean</span>
    <span class="gm-chip" data-gf="sorry">sorry</span><span class="gm-chip" data-gf="empty">no lean</span>
    <span class="sp"></span>
    <button class="gm-btn" id="gmCollapseAll" title="Collapse every expanded chapter back to the overview">Collapse all</button>
    <button class="gm-btn" id="gmFit">Fit</button>
    <button class="gm-btn" id="gmClose">✕ Close</button>
  </div>
  <div class="gm-body">
    <div class="gm-wrap">
      <canvas id="gcanvas"></canvas>
      <div id="gviz" class="gm-gviz" style="display:none"></div>
      <div class="gm-float gm-count" id="gmCount"></div>
      <div class="gm-float gm-legend" id="gmLegendPanel" style="display:flex">
        <div class="lgttl" id="gmLegToggle" title="Click to collapse/expand">Legend <span class="lgcar">▾</span><br><span class="lgsub">Shape = kind · border = statement · fill = proof</span></div>
        <div class="lgsec">Chapters</div>
        <div class="lg"><i class="lgf" style="background:#ede9fe;border:2px solid #7c3aed"></i>collapsed — click to expand</div>
        <div class="lg"><i class="lgf" style="background:#f3effc;border:2px solid #7c3aed;border-radius:2px"></i>expanded — click background to collapse</div>
        <div class="lgsec">Shape</div>
        <div class="lg"><i class="lgshape rect"></i>definition</div><div class="lg"><i class="lgshape ell"></i>theorem / lemma / corollary</div>
        <div class="lgsec">Statement (border)</div>
        <div class="lg"><i class="lgb" style="border-color:#b0bec5"></i>blocked</div><div class="lg"><i class="lgb" style="border-color:#1565c0"></i>ready to formalize</div><div class="lg"><i class="lgb" style="border-color:#2e7d32"></i>formalized</div>
        <div class="lgsec">Proof (fill)</div>
        <div class="lg"><i class="lgf" style="background:#eef1f4"></i>not ready</div><div class="lg"><i class="lgf" style="background:#bbdefb"></i>ready to formalize</div><div class="lg"><i class="lgf" style="background:#ffcc80"></i>Lean code incomplete</div><div class="lg"><i class="lgf" style="background:#c8e6c9"></i>locally formalized</div><div class="lg"><i class="lgf" style="background:#66bb6a"></i>+ dependencies complete</div>
        <div class="lgsec">Edges</div>
        <div class="lg"><span class="lge"></span>statement dependency</div><div class="lg"><span class="lge dash"></span>proof dependency</div>
      </div>
      <div class="gm-float gm-hint">drag to pan · scroll to zoom · click a node · in an overview click a box to drill in · <b>Detail</b> filters coarse/medium/fine · <b>Legend</b> explains colours</div>
    </div>
    <aside id="gm-side" class="empty"></aside>
  </div>
</div>
<script>
const MACROS=/*__MACROS__*/{}, LIVE=/*__LIVE__*/false;
let DATA=/*__DATA__*/null, BYID={}, BYLBL={}, REV={}, REFS={}, LOC={}, LEANCODE={}, CITES={}, BIB={}, curCh=0, curView="doc";
const GVSVG=/*__GVSVG__*/null;   /* build-time Graphviz layout (full/groups), or null → client WASM fallback */
const S=["mathlib_ok","lean_ok","sorry","empty"], active=new Set();
function esc(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}
function abbrOf(k){return ({definition:"Def",lemma:"Lem",theorem:"Thm",proposition:"Prop",corollary:"Cor",remark:"Rmk",example:"Ex",conjecture:"Conj"}[k])||(k[0].toUpperCase()+k.slice(1))}
function xref(labels){return labels.split(",").map(l=>{l=l.trim();const r=REFS[l];
  if(r&&r.id)return `<a class="ref" data-id="${r.id}">${r.abbr}&nbsp;${r.num}</a>`;
  if(r)return `<span class="ref" style="color:var(--muted);cursor:default">${r.abbr}&nbsp;${r.num}</span>`;
  return `<span class="xref">${esc(l.replace(/^[a-z]+:/,''))}</span>`}).join(", ")}
/* text-mode LaTeX → HTML; math ( \(..\), \[..\], $..$ ) left untouched for KaTeX */
/* Resolve text-formatting macros innermost-first so nested braces render, e.g.
   \textit{Source: \texttt{Foo.Bar} in \texttt{A/B.lean}, L44--L440} → all levels. */
const _IMRULES=[
  [/\\paragraph\{([^{}]*)\}/g,"<b>$1.</b> "],
  [/\\(?:sub)*section\*?\{([^{}]*)\}/g,"<strong>$1</strong> "],
  [/\\(?:emph|textit|textsl|textsc)\{([^{}]*)\}/g,"<em>$1</em>"],
  [/\\textbf\{([^{}]*)\}/g,"<strong>$1</strong>"],
  [/\{\\(?:bfseries|bf)(?![a-zA-Z])\s*([^{}]*)\}/g,"<strong>$1</strong>"],
  [/\{\\(?:itshape|slshape|emph|em|it|sl)(?![a-zA-Z])\s*([^{}]*)\}/g,"<em>$1</em>"],
  [/\{\\(?:ttfamily|tt)(?![a-zA-Z])\s*([^{}]*)\}/g,"<code>$1</code>"],
  [/\{\\(?:normalfont|rmfamily|sffamily|scshape|rm|sf|sc)(?![a-zA-Z])\s*([^{}]*)\}/g,"$1"],
  [/\\(?:texttt|verb|lstinline)\{([^{}]*)\}/g,"<code>$1</code>"],
  [/\\href\{([^{}]*)\}\{([^{}]*)\}/g,'<a href="$1" target="_blank" rel="noopener">$2</a>'],
  [/\\url\{([^{}]*)\}/g,'<a href="$1" target="_blank" rel="noopener">$1</a>'],
  [/\\texorpdfstring\{([^{}]*)\}\{[^{}]*\}/g,"$1"],
  [/\\[cC]ref\{([^{}]*)\}/g,(m,a)=>xref(a)],
  [/\\(?:eq)?ref\{([^{}]*)\}/g,(m,a)=>xref(a)],
  [/\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])?\{([^{}]*)\}/g,(m,a)=>a.split(",").map(k=>{k=k.trim();return `<a class="cite" data-cite="${esc(k)}">[${esc(k)}]</a>`}).join(", ")],
];
function inlineMacros(s){let prev,i=0;
  do{prev=s;for(const [re,rep] of _IMRULES)s=s.replace(re,rep)}while(s!==prev&&++i<10);
  return s;}
const _ACC={"'":"́","`":"̀","^":"̂",'"':"̈","~":"̃","=":"̄",".":"̇","v":"̌","u":"̆","c":"̧","H":"̋","r":"̊"};
function detexRest(s){
  s=s.replace(/\\(['`^"~=.]|[vucHr](?![A-Za-z]))(?:\s*\{([A-Za-z])\}|([A-Za-z]))/g,(_,a,br,ba)=>((br||ba||"")+_ACC[a]).normalize("NFC"));
  s=s.replace(/``/g,"“").replace(/''/g,"”").replace(/---/g,"—").replace(/ -- /g," – ");
  /* drop spacing / layout commands that carry no text (\noindent, \smallskip, …) */
  s=s.replace(/\\(?:noindent|indent|par|smallskip|medskip|bigskip|vfill|hfill|newpage|clearpage|pagebreak|nopagebreak|linebreak|centering|raggedright|raggedleft|samepage|sloppy|protect|leavevmode|frenchspacing|allowbreak|maketitle|bfseries|itshape|normalfont|scshape|ttfamily|footnotesize|small|large|Large|normalsize)\b\s*/g,"");
  /* \item[label] → a list item whose marker is the given label; \item → plain item */
  s=s.replace(/\\item\s*\[([^\]]*)\]\s*/g,'</li><li class="li-lbl"><span class="li-mark">$1</span> ');
  s=s.replace(/\\begin\{itemize\}/g,"<ul>").replace(/\\end\{itemize\}/g,"</ul>")
     .replace(/\\begin\{enumerate\}/g,"<ol>").replace(/\\end\{enumerate\}/g,"</ol>")
     .replace(/\\begin\{description\}/g,"<ul>").replace(/\\end\{description\}/g,"</ul>").replace(/\\item\s*/g,"</li><li>");
  s=s.replace(/<(ul|ol)><\/li>/g,"<$1>");
  /* commands whose braced argument adds nothing to prose, and footnotes → parenthetical */
  s=s.replace(/\\(?:label|hspace\*?|vspace\*?|phantom|hphantom|vphantom|vskip|hskip|setlength|index|footnotemark)\{[^{}]*\}/g,"");
  /* structural / provenance markers: metadata, not prose — strip so they never leak as raw TeX */
  s=s.replace(/\\(?:dcref|group|level|lean|uses|proves|label|source)\{[^{}]*\}/g,"").replace(/\\(?:leanok|notready|mathlibok)\b/g,"");
  s=s.replace(/\\footnote\{([^{}]*)\}/g," ($1)");
  /* theorem-like / block environments that leak into a prose body → label them, don't dump raw */
  s=s.replace(/\\begin\{quote\}/g,"<blockquote>").replace(/\\end\{quote\}/g,"</blockquote>");
  const _envLbl=(m,e)=>'<em class="env-lbl">'+e.charAt(0).toUpperCase()+e.slice(1)+'.</em> ';
  s=s.replace(/\\begin\{(proof|claim|lemma|theorem|proposition|corollary|definition|remark|example|conjecture|sublemma|scholium|note)\}\s*/g,_envLbl)
     .replace(/\\end\{(?:proof|claim|lemma|theorem|proposition|corollary|definition|remark|example|conjecture|sublemma|scholium|note)\}\s*/g," ");
  s=s.replace(/\\(?:begin|end)\{[a-zA-Z*]+\}\s*/g,"");   /* any other stray environment wrapper → drop cleanly (braces and all) */
  /* bare font / spacing switches that carry no text */
  s=s.replace(/\\(?:it|rm|bf|sl|sc|tt|sf|em|quad|qquad|nobreak|goodbreak|hfil|hfill|vfil|vfill|thinspace|enspace|display|textstyle|scriptstyle|displaystyle)\b\s*/g,"");
  s=s.replace(/\{\\v ([A-Za-z])\}/g,"$1̌").replace(/\\%/g,"%").replace(/\\&/g,"&amp;").replace(/\\#/g,"#").replace(/\\_/g,"_").replace(/\\ /g," ").replace(/\\,|\\;|\\!|\\:/g," ");
  s=s.replace(/\\\{/g,"&#123;").replace(/\\\}/g,"&#125;");   /* escaped literal braces, protected from the strip below */
  s=s.replace(/\\\\\s*/g,"<br>").replace(/(?<!\\)~/g," ");
  s=s.replace(/\{\\(?:[a-zA-Z]+)\b\s*|[{}]/g,"");            /* drop leftover TeX grouping braces / font switches */
  s=s.replace(/[ \t]*\n[ \t]*\n[ \t]*/g,"</p><p>");
  s=s.replace(/[ \t]{2,}/g," ");
  return s;
}
/* Wrap standalone display-math environments so KaTeX renders them: equation →
   \[…\]; align/gather/eqnarray/multline → \[\begin{aligned|gathered}…\]. KaTeX
   can't parse these at top level, and its auto-render only knows $ … \[ … \( . */
function mathEnvs(s){const strip=b=>b.replace(/\\label\{[^{}]*\}/g,"").replace(/\\(?:notag|nonumber)\b/g,"").replace(/(\\begin\{array\})\s*\[[a-zA-Z]\]/g,"$1");
  /* protect existing math so only top-level (bare) environments get wrapped */
  const M=[],prot=x=>x.replace(/(\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$|\$[^$]*?\$)/g,m=>{M.push(m);return "@@KE"+(M.length-1)+"EK@@"});
  s=prot(s);
  s=s.replace(/\\begin\{equation\*?\}([\s\S]*?)\\end\{equation\*?\}/g,(m,b)=>`\\[${strip(b)}\\]`);
  s=s.replace(/\\begin\{(eqnarray\*?|align\*?|alignat\*?|flalign\*?|gather\*?|multline\*?)\}([\s\S]*?)\\end\{\1\}/g,(m,env,b)=>{
    const inner=/^gather/.test(env)?"gathered":"aligned";
    if(/^eqnarray/.test(env))b=b.replace(/&\s*([^&\n]*?)\s*&/g,"&$1");   /* 3-col eqnarray → 1-col align */
    else if(/^alignat/.test(env))b=b.replace(/^\s*\{?\d+\}?/,"");        /* drop the column-count arg */
    return `\\[\\begin{${inner}}${strip(b)}\\end{${inner}}\\]`;});
  s=prot(s);   /* protect the \[…\] just produced, so the bare-env pass below skips them */
  /* bare display environments (aligned/array/cases/matrix/…) at top level → wrap in \[…\] */
  s=s.replace(/(\\begin\{(aligned|alignedat|gathered|split|array|cases|dcases|smallmatrix|matrix|bmatrix|Bmatrix|pmatrix|vmatrix|Vmatrix)\}[\s\S]*?\\end\{\2\})/g,m=>`\\[${strip(m)}\\]`);
  return s.replace(/@@KE(\d+)EK@@/g,(_,i)=>M[+i]);}
/* text-mode LaTeX → HTML. Math ($…$, \(…\), \[…\], $$…$$) is pulled out to sentinels
   so text macros ({\bf …}, \textbf{…}) resolve even across math, then restored for KaTeX. */
function detex(s){s=esc(mathEnvs(String(s||"")));
  const math=[];
  s=s.replace(/(\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$|\$[^$]*?\$)/g,m=>{math.push(m);return "@@KX"+(math.length-1)+"XK@@"});
  s=detexRest(inlineMacros(s));
  return s.replace(/@@KX(\d+)XK@@/g,(_,i)=>math[+i]);}
function proseHtml(s){let h="<p>"+detex(s)+"</p>";return h.replace(/<p>\s*<\/p>/g,"")}
/* \mbox/\hbox → \text so KaTeX renders text (incl. nested $…$) inside math */
const _KMACROS=Object.assign({"\\mbox":"\\text","\\hbox":"\\text"},(typeof MACROS==="object"&&MACROS)||{});
function typeset(el){if(el&&window.renderMathInElement)renderMathInElement(el,{delimiters:[
  {left:"\\[",right:"\\]",display:true},{left:"\\(",right:"\\)",display:false},
  {left:"$$",right:"$$",display:true},{left:"$",right:"$",display:false}],macros:_KMACROS,throwOnError:false})}
/* Typesetting a whole chapter at once is the main navigation cost (hundreds of
   KaTeX spans → ~1s). Instead, KaTeX only the blocks near the viewport now and
   render the rest as they scroll in — the chapter appears instantly. */
let _mathObs=null;
function typesetLazy(el){
  if(!el||!window.renderMathInElement)return;
  if(_mathObs){_mathObs.disconnect();_mathObs=null}
  const blocks=el.querySelectorAll(".stmt,.prose,.proof,h2.ch,.choverview,.maketitle,.sumcard,.bibitem");
  if(blocks.length<8){typeset(el);return}
  const seen=new WeakSet();
  _mathObs=new IntersectionObserver((es,o)=>{for(const e of es){if(!e.isIntersecting)continue;
    if(!seen.has(e.target)){seen.add(e.target);typeset(e.target)}o.unobserve(e.target)}},{rootMargin:"1000px 0px"});
  blocks.forEach(b=>_mathObs.observe(b));
}
function leanHi(code){let s=esc(code);const cm=[];
  s=s.replace(/(\/-[\s\S]*?-\/|--[^\n]*)/g,m=>{cm.push(m);return "@@CM"+(cm.length-1)+"@@"});
  s=s.replace(/\b(theorem|lemma|def|abbrev|instance|structure|class|inductive|where|by|fun|let|in|match|with|do|if|then|else|from|have|show|calc|open|namespace|end|variable|universe|section|example|noncomputable|private|protected|import)\b/g,'<span class="c-kw">$1</span>');
  s=s.replace(/@@CM(\d+)@@/g,(m,i)=>`<span class="c-cm">${cm[+i]}</span>`);
  return s;}
function sb(st){return `<span class="b b-${st}">${st.replace('_',' ')}</span>`}
function index(){BYID={};BYLBL={};REV={};LEANCODE={};CITES={};BIB={};REFS=DATA.refs||{};LOC=DATA.loc||{};
  (DATA.bib||[]).forEach((b,i)=>{b._n=i+1;BIB[b.key]=b});
  const cre=/\\cite[tp]?\*?\{([^{}]*)\}/g;
  for(const e of DATA.entries){BYID[e.id]=e;if(e.label)BYLBL[e.label]=e.id;
    e.deps.forEach(d=>{(REV[d.id]=REV[d.id]||[]).push(e.id)});
    e.lean.forEach(l=>{if(l.code)LEANCODE[l.name]=l.code});
    let m;cre.lastIndex=0;while((m=cre.exec(e.body||""))){m[1].split(",").forEach(k=>{k=k.trim();if(k)(CITES[k]=CITES[k]||[]).push(e.id)})}}}

/* ---- statement box: compact hoverable tags (uses / used-by / Lean) ---- */
function metaTags(en,id){if(!en)return"";const t=[];
  const up=(en.deps||[]).length,down=(REV[id]||[]).length;
  t.push(`<span class="mtag pop" data-graph="${id}">uses ${up} · used by ${down}</span>`);
  if(en.lean&&en.lean.length)t.push(`<span class="mtag pop lean" data-lean="${id}">✓ L∃∀N · ${en.lean.length}</span>`);
  else if(en.mathlib_name)t.push(`<span class="mtag pop mathlib" data-lean="${id}">mathlib</span>`);
  return `<div class="smeta">${t.join("")}</div>`}
function stmtBox(b){const en=b.enrich,st=en?en.lean_status:"empty";
  return `<div class="stmt k-${b.content_type} s-${st}" id="stmt-${b.id||''}" ${b.id?'data-id="'+b.id+'"':''} data-status="${st}">
    <div class="sh"><span class="tag k-${b.content_type}">${b.abbr}&nbsp;${b.num}</span>${b.title&&b.title!==b.label?`<span class="st">${detex(b.title)}</span>`:''}<span class="badges">${en&&en.ref?`<span class="reftag" title="source reference">${esc(en.ref)}</span>`:''}${en&&en.group?`<span class="grptag" title="group">${esc(en.group)}</span>`:''}${en?sb(st):''}</span></div>
    <div class="sbody">${proseHtml(b.body)}</div>
    ${b.id?metaTags(en,b.id):''}</div>`;
}
function block(b){
  if(b.t==="head"){const l=b.level>4?4:b.level;return `<h${l}${b.num?` id="sec-${esc(b.num)}"`:''}>${b.num?`<span class="hn">${b.num}</span>`:''}${detex(b.title)}</h${l}>`}
  if(b.t==="prose")return `<div class="prose">${proseHtml(b.tex)}</div>`;
  if(b.t==="stmt")return stmtBox(b);
  if(b.t==="proof")return `<details class="proof"><summary>Proof</summary><div class="pbody">${proseHtml(b.tex)}</div></details>`;
  return "";
}
function chapterSections(ch){const rows=[];let cur=null;
  for(const b of ch.blocks){
    if(b.t==="head"&&b.level>=2&&b.level<=3&&b.num){cur={num:b.num,title:b.title,level:b.level,stmts:[]};rows.push(cur)}
    else if(b.t==="stmt"){if(!cur){cur={num:"",title:"",level:2,stmts:[]};rows.push(cur)}cur.stmts.push(b)}}
  return rows}
/* two-level tree (section → subsections) for the Overview page's drill-down —
   unlike chapterSections() (a flat list, used for indentation only elsewhere),
   this actually nests level-3 subsections under their level-2 parent so the
   squares can be re-partitioned one level at a time. */
function chapterTree(ch){const secs=[];let sec=null;
  const own=()=>{if(!sec){sec={num:"",title:"",stmts:[],subs:[]};secs.push(sec)}return sec};
  for(const b of ch.blocks){
    if(b.t==="head"&&b.level===2&&b.num){sec={num:b.num,title:b.title,stmts:[],subs:[]};secs.push(sec)}
    else if(b.t==="head"&&b.level===3&&b.num){own().subs.push({num:b.num,title:b.title,stmts:[]})}
    else if(b.t==="stmt"){const s=own();(s.subs.length?s.subs[s.subs.length-1]:s).stmts.push(b)}}
  return secs}
function chapterOverview(ch,i){const col={mathlib_ok:'#0b5fd0',lean_ok:'#137333',sorry:'#d11a2a',empty:'#9aa2ad'};
  const stmts=ch.blocks.filter(b=>b.t==="stmt"),rows=chapterSections(ch);if(!stmts.length&&!rows.length)return"";
  const cc={mathlib_ok:0,lean_ok:0,sorry:0,empty:0};stmts.forEach(b=>{const s=b.enrich?b.enrich.lean_status:'empty';cc[s]=(cc[s]||0)+1});
  const p=stmts.length?Math.round(100*(cc.lean_ok+cc.mathlib_ok)/stmts.length):0;
  const rowsHtml=rows.map(r=>{const sq=r.stmts.map(b=>{const st=b.enrich?b.enrich.lean_status:'empty';
      return `<i class="mm" style="background:${col[st]}" data-goto="${b.id||''}"></i>`}).join("");
    const label=r.num?`<div class="co-sec l${r.level}" data-ch="${i}" data-sec="${esc(r.num)}"><span class="n">${esc(r.num)}</span>${detex(r.title)}</div>`
      :`<span class="co-sec" style="color:var(--muted)">Introduction</span>`;
    return `<div class="co-row">${label}<div class="mmcells co-rowmap">${sq}</div></div>`}).join("");
  return `<details class="choverview" open><summary>Chapter contents · <b>${stmts.length}</b> statements · <b>${p}%</b> formalized</summary>${rowsHtml}</details>`}
function renderChapter(i){curCh=i;curView="doc";setNav(null);const ch=DATA.chapters[i],main=document.getElementById("main");main.classList.remove("results");
  main.innerHTML=`<h2 class="ch"><span class="hn">${ch.num}</span>${detex(ch.title)}</h2>`+chapterOverview(ch,i)+ch.blocks.map(block).join("");
  typesetLazy(main);window.scrollTo(0,0);renderTOC();renderOutline();}
function chapterStats(ch){let n=0;for(const b of ch.blocks)if(b.t==="stmt")n++;return n}
/* sidebar expand/collapse state — deliberately independent of curCh/navigation:
   nothing auto-expands just because you're reading that chapter. ch: Set<int>,
   sec: Set<"chapterIndex:sectionNum"> (only sections that have subsections use it). */
const TOC_OPEN={ch:new Set(),sec:new Set()};
function renderTOC(){const toc=document.getElementById("toc");
  toc.innerHTML=DATA.chapters.map((ch,i)=>{
    const chOpen=TOC_OPEN.ch.has(i);
    let sub="";
    /* plain text hierarchy only — no status squares here, that's what the main
       "Overview" page's chapter/section boxes are for */
    if(chOpen)sub=chapterTree(ch).filter(s=>s.num).map(s=>{
      const key=i+":"+s.num,hasSubs=s.subs.length>0,secOpen=TOC_OPEN.sec.has(key);
      const chev=hasSubs?`<span class="tchev" data-toggle-sec="${esc(key)}">${secOpen?'▾':'▸'}</span>`:`<span class="tchev-sp"></span>`;
      const subsHtml=(hasSubs&&secOpen)?s.subs.map(u=>
        `<div class="tsec l3" data-ch="${i}" data-sec="${esc(u.num)}"><span class="tchev-sp"></span><span class="n">${esc(u.num)}</span><span>${detex(u.title)}</span></div>`).join(""):"";
      return `<div class="tsec" data-ch="${i}" data-sec="${esc(s.num)}">${chev}<span class="n">${esc(s.num)}</span><span>${detex(s.title)}</span></div>${subsHtml}`;
    }).join("");
    const chChev=`<span class="tchev" data-toggle-ch="${i}">${chOpen?'▾':'▸'}</span>`;
    return `<div data-ch="${i}" class="tch${i===curCh?' sel':''}">${chChev}<span class="n">${ch.num}</span><span>${detex(ch.title)}</span><span class="c">${chapterStats(ch)}</span></div>${sub}`}).join("");typeset(toc)}

/* ---- right outline: the current chapter's statements, status + quick jump ---- */
const OCOL={mathlib_ok:"#0b5fd0",lean_ok:"#137333",sorry:"#d11a2a",empty:"#9aa2ad"};
let olObs=null;
function plainTex(s){return String(s||"").replace(/\\[a-zA-Z]+\s?/g," ").replace(/[{}$\\]/g,"").replace(/\s+/g," ").trim()}
function renderOutline(){const out=document.getElementById("outline");if(!out)return;
  if(olObs){olObs.disconnect();olObs=null}
  if(curView!=="doc"){out.innerHTML=`<div class="olh">Outline</div><div class="oempty">The chapter outline appears while reading the blueprint.</div>`;return}
  if(resultsMode()){out.innerHTML=`<div class="olh">Outline</div><div class="oempty">Filtered results shown — clear search &amp; filters to see the chapter outline.</div>`;return}
  const ch=DATA.chapters&&DATA.chapters[curCh];if(!ch){out.innerHTML="";return}
  let items="",pending="",n=0;
  for(const b of ch.blocks){
    if(b.t==="head"&&b.level===2&&b.num){pending=`<div class="olsec">${esc(b.num)} ${esc(plainTex(b.title))}</div>`;continue}
    if(b.t!=="stmt")continue;
    if(pending){items+=pending;pending=""}
    n++;const en=b.enrich,st=en?en.lean_status:"empty";
    const title=b.title&&b.title!==b.label?detex(b.title):`<span style="color:var(--muted)">${esc((b.label||"").replace(/^[a-z]+:/,""))}</span>`;
    items+=`<a class="omini k-${b.content_type}" data-oli="${b.id||""}" title="${esc(plainTex(b.title||b.label))}">`
      +`<div class="omini-h"><span class="tag k-${b.content_type}">${b.abbr}&nbsp;${b.num}</span><span class="omini-b">${en?sb(st):''}</span></div>`
      +`<div class="otitle2">${title}</div></a>`;
  }
  out.innerHTML=`<div class="olh">In this chapter <span class="olc">${n}</span></div>`
    +(items?`<div class="olist">${items}</div>`:`<div class="oempty">No statements in this chapter.</div>`);
  typeset(out);spyOutline();
}
function spyOutline(){const boxes=[...document.querySelectorAll("#main .stmt[id^='stmt-']")];
  if(!boxes.length||!window.IntersectionObserver)return;
  const links={};document.querySelectorAll("#outline .omini[data-oli]").forEach(a=>{if(a.dataset.oli)links[a.dataset.oli]=a});
  const vis=new Set();
  olObs=new IntersectionObserver(es=>{es.forEach(e=>{const id=e.target.id.slice(5);e.isIntersecting?vis.add(id):vis.delete(id)});
    let cur=null;for(const b of boxes){if(vis.has(b.id.slice(5))){cur=b.id.slice(5);break}}
    Object.values(links).forEach(a=>a.classList.remove("cur"));
    if(cur&&links[cur]){links[cur].classList.add("cur");
      const a=links[cur],p=a.parentElement;if(p&&(a.offsetTop<p.scrollTop||a.offsetTop>p.scrollTop+p.clientHeight-30))a.scrollIntoView({block:"nearest"})}
  },{rootMargin:"-90px 0px -55% 0px"});
  boxes.forEach(b=>olObs.observe(b));
}

/* ---- filter / search → results list ---- */
function filtered(){const q=document.getElementById("q").value.trim().toLowerCase(),sf=S.filter(s=>active.has(s));
  return DATA.entries.filter(e=>{
    if(sf.length&&!sf.includes(e.lean_status))return false;
    if(q){const h=(e.title+" "+(e.label||"")+" "+e.lean.map(l=>l.name).join(" ")).toLowerCase();if(!h.includes(q))return false}
    return true})}
function resultsMode(){return document.getElementById("q").value.trim()||active.size}
function renderResults(){curView="doc";setNav(null);const rows=filtered(),main=document.getElementById("main");main.classList.add("results");
  main.innerHTML=`<h2 class="ch">${rows.length} statement${rows.length===1?'':'s'}</h2>`+rows.slice(0,300).map(e=>{const r=REFS[e.label]||{};
    return `<div class="stmt k-${e.kind} s-${e.lean_status}" data-id="${e.id}" data-nav="1"><div class="sh"><span class="tag k-${e.kind}">${r.abbr||abbrOf(e.kind)}&nbsp;${r.num||''}</span><span class="st">${detex(e.title)}</span><span class="badges">${sb(e.lean_status)}</span></div><div class="smeta"><span>${esc(e.chapter||'')}</span></div></div>`}).join("")
    +(rows.length>300?`<div class="ro">Showing first 300 of ${rows.length}.</div>`:"");typesetLazy(main);renderOutline()}
function update(){if(resultsMode())renderResults();else renderChapter(curCh)}

/* ---- summary + bibliography views ---- */
function segbar(cc,total){const seg=(k,col)=>cc[k]?`<i style="width:${100*cc[k]/total}%;background:${col}"></i>`:"";
  return `<div class="segbar" title="mathlib ${cc.mathlib_ok||0} · lean ${cc.lean_ok||0} · sorry ${cc.sorry||0} · none ${cc.empty||0}">${seg('mathlib_ok','#0b5fd0')}${seg('lean_ok','#137333')}${seg('sorry','#d11a2a')}${seg('empty','#c7ccd4')}</div>`}
function clearControls(){document.getElementById("q").value="";active.clear();document.querySelectorAll(".chip.on").forEach(c=>c.classList.remove("on"))}
function setNav(id){document.querySelectorAll(".navlink").forEach(a=>a.classList.toggle("on",a.id===id))}
let SUM=null,_readyAll=false;
function computeSummary(){if(SUM)return SUM;const es=DATA.entries;
  const F=e=>!!e&&(e.lean_status==="lean_ok"||e.lean_status==="mathlib_ok");
  const cm={},cst={};                                    /* fully-closed = self + all transitive deps formalized */
  function closed(e){if(!e)return false;const id=e.id;if(cm[id]!==undefined)return cm[id];
    if(cst[id])return F(e);cst[id]=1;let r=F(e);if(r)for(const d of e.deps){if(!closed(BYID[d.id])){r=false;break}}cst[id]=0;return cm[id]=r}
  es.forEach(closed);
  const dcache={};function unlocks(id){if(dcache[id]!=null)return dcache[id];const seen=new Set(),st=[...(REV[id]||[])];
    while(st.length){const x=st.pop();if(seen.has(x))continue;seen.add(x);(REV[x]||[]).forEach(y=>{if(!seen.has(y))st.push(y)})}return dcache[id]=seen.size}
  const rows=es.map(e=>({e,F:F(e),closed:cm[e.id],ready:!F(e)&&e.deps.every(d=>F(BYID[d.id])),
    uses:e.deps.length,unlocks:unlocks(e.id)}));
  const g=k=>rows.filter(k);
  SUM={rows,total:es.length,completed:g(r=>r.closed).length,
    sorries:es.filter(e=>e.lean_status==="sorry").length,noProof:es.filter(e=>e.lean_status==="empty").length,
    depsInc:g(r=>r.F&&!r.closed).length,
    ready:g(r=>r.ready).sort((a,b)=>b.unlocks-a.unlocks),
    blockers:es.filter(e=>e.lean_status==="sorry")};
  SUM.readyN=SUM.ready.length;SUM.actionable=SUM.ready.filter(r=>r.unlocks>0).length;
  return SUM}
function sumBox(e,st,meta){const rf=REFS[e.label]||{};
  return `<div class="stmt sum hovprev k-${e.kind} s-${st}" data-id="${e.id}" data-nav="1">
    <div class="sh"><span class="tag k-${e.kind}">${rf.abbr||abbrOf(e.kind)}${rf.num?'&nbsp;'+rf.num:''}</span><span class="st">${detex(e.title||e.label||e.id)}</span><span class="badges">${sb(st)}</span></div>
    ${meta?`<div class="rmeta">${meta}</div>`:''}</div>`}
function readyItem(r){const e=r.e,stage=e.lean_status==="sorry"?"proof":"statement";
  return sumBox(e,e.lean_status,`<span class="p">stage: <b>${stage}</b></span><span class="p">direct uses <b>${r.uses}</b></span><span class="p">downstream unlocks <b>${r.unlocks}</b></span>${e.lean&&e.lean.length?`<span class="p">Lean: <b>${e.lean.length}</b></span>`:''}`)}
function renderSummary(){curView="summary";clearControls();setNav("sumbtn");const main=document.getElementById("main");main.classList.remove("results");
  const s=computeSummary();
  const cards=[
    {v:s.total,l:'Total entries',x:`completed ${s.completed} · deps incomplete ${s.depsInc} · sorries ${s.sorries} · no proof ${s.noProof}`},
    {v:s.readyN,l:'Ready now',x:'entries whose next formalization step is unblocked'},
    {v:s.completed,l:'Fully closed',x:'local code and prerequisite closure both complete'},
    {v:s.actionable,l:'Actionable priorities',x:'ready now and already unlocking downstream work'},
    {v:s.sorries,l:'Current blockers',x:'declarations with a sorry / incomplete Lean'}];
  const readyShown=_readyAll?s.ready:s.ready.slice(0,12);
  const readyHtml=s.ready.length?readyShown.map(readyItem).join("")+
    (s.ready.length>12?`<div class="morebtn" id="readyMore">${_readyAll?'Show fewer':'Show all '+s.ready.length+' ready entries'}</div>`:''):'<div class="ro">Nothing is unblocked right now.</div>';
  const blockHtml=s.blockers.length?s.blockers.slice(0,40).map(e=>{const decl=(e.lean||[]).filter(l=>l.status==="sorry").map(l=>l.name).join(", ")||(e.lean||[]).map(l=>l.name).join(", ");
    return sumBox(e,"sorry",decl?`<span class="p">sorry in <b>${esc(decl)}</b></span>`:"")}).join(""):'<div class="ro">No sorries — nothing blocked.</div>';
  let chRows="";(DATA.chapters||[]).forEach((ch,i)=>{const st=ch.blocks.filter(b=>b.t==="stmt");if(!st.length)return;
    const cc={mathlib_ok:0,lean_ok:0,sorry:0,empty:0};st.forEach(b=>{const x=b.enrich?b.enrich.lean_status:'empty';cc[x]=(cc[x]||0)+1});
    const p=Math.round(100*(cc.lean_ok+cc.mathlib_ok)/st.length);
    chRows+=`<tr><td><a data-ch="${i}">${ch.num} ${detex(ch.title)}</a></td><td>${st.length}</td><td><div style="display:flex;gap:9px;align-items:center">${segbar(cc,st.length)}<span style="color:var(--muted)">${p}%</span></div></td></tr>`});
  main.innerHTML=`<h2 class="ch">Blueprint summary</h2>
    <div class="sumgrid">${cards.map(c=>`<div class="sumcard"><div class="v">${c.v}</div><div class="l">${c.l}</div>${c.x?`<div class="s">${c.x}</div>`:''}</div>`).join("")}</div>
    <div class="sumsec">Ready next (${s.ready.length})</div>${readyHtml}
    <div class="sumsec">Current blockers (${s.blockers.length})</div>${blockHtml}
    ${DATA.chapters?`<div class="sumsec">Structure &amp; coverage</div><table class="sumtable"><thead><tr><th>Chapter</th><th>#</th><th>progress</th></tr></thead><tbody>${chRows}</tbody></table>`:''}`;
  typesetLazy(main);window.scrollTo(0,0);renderOutline();}
function bibAuthors(a){if(!a)return"";return a.split(/\s+and\s+/).map(p=>{p=p.trim();
  if(p.includes(",")){const i=p.indexOf(",");return (p.slice(i+1).trim()+" "+p.slice(0,i).trim()).trim()}return p}).join(", ")}
function fmtBib(b){const au=bibAuthors(b.author);let s="";
  if(au)s+=`<span style="font-weight:600">${esc(au)}</span>`;
  if(b.year)s+=` (${esc(b.year)})`;s+=au||b.year?". ":"";
  s+=`“${detex(b.title||b.key)}”.`;
  if(b.journal||b.booktitle)s+=` <em>${detex(b.journal||b.booktitle)}</em>.`;
  const vp=[];if(b.volume)vp.push(b.number?`${esc(b.volume)}(${esc(b.number)})`:esc(b.volume));
  if(b.pages)vp.push("pp. "+esc(b.pages).replace(/--/g,"–"));
  if(vp.length)s+=" "+vp.join(", ")+".";
  if(b.publisher&&!(b.journal||b.booktitle))s+=` ${detex(b.publisher)}.`;
  return s}
function renderBiblio(){curView="biblio";clearControls();setNav("bibbtn");const main=document.getElementById("main");main.classList.remove("results");
  const bib=DATA.bib||[];
  main.innerHTML=`<h2 class="ch">Blueprint bibliography <span style="color:var(--muted);font-weight:400;font-size:18px">(${bib.length})</span></h2>`+(bib.length
    ?`<div>${bib.map((b,i)=>{const cb=CITES[b.key]||[];
      const cites=cb.length?': '+cb.map(id=>{const e=BYID[id];if(!e)return'';const r=REFS[e.label]||{};return `<a class="ref" data-id="${id}">${r.abbr?r.abbr+'&nbsp;'+r.num:esc((e.label||id).replace(/^[a-z]+:/,''))}</a>`}).filter(Boolean).join(", "):'';
      return `<div class="bibitem" data-key="${esc(b.key)}"><div class="bi-t"><span class="bi-n">[${i+1}]</span> ${fmtBib(b)}${b.url?` <a href="${esc(b.url)}" target="_blank" rel="noopener" title="open">↗</a>`:''}</div><div class="bi-c">Cited from (${cb.length})${cites}</div></div>`}).join("")}</div>`
    :`<div class="ro">No bibliography found. Drop a <code>.bib</code> next to the blueprint and it appears here; <code>\\cite{…}</code> in the text will link to it.</div>`);
  typesetLazy(main);window.scrollTo(0,0);renderOutline();}

function stats(){const es=DATA.entries;const c={total:es.length};S.forEach(s=>c[s]=0);
  es.forEach(e=>{c[e.lean_status]=(c[e.lean_status]||0)+1});
  const pct=Math.round(100*(c.lean_ok+c.mathlib_ok)/Math.max(1,c.total));
  document.getElementById("stats").innerHTML=
    `<span class="stat"><b>${c.total}</b> statements</span><span class="stat" style="color:var(--mathlib)"><b>${c.mathlib_ok}</b> mathlib</span>`+
    `<span class="stat" style="color:var(--lean)"><b>${c.lean_ok}</b> lean</span><span class="stat" style="color:var(--sorry)"><b>${c.sorry}</b> sorry</span>`+
    `<span class="stat"><b>${pct}%</b> formalized<span class="bar"><i style="width:${pct}%"></i></span></span>`;}

/* ---- hover preview (statements + lean code) ---- */
const pv=document.getElementById("pv");let pvT,pvHideT,pvPinned=false;
function showPv(html,x,y){pv.innerHTML=html;pv.classList.toggle("pv-graph",!!pv.querySelector(".pv-graphwrap"));pv.style.display="block";const w=pv.offsetWidth,h=pv.offsetHeight;
  pv.style.left=Math.min(x+14,innerWidth-w-10)+"px";pv.style.top=Math.max(10,Math.min(y+16,innerHeight-h-10))+"px";typeset(pv)}
function showPvPinned(html,x,y){pvPinned=false;showPv(html,x,y);pvPinned=true}
function hidePv(){pv.style.display="none";pvPinned=false}
function schedHide(){clearTimeout(pvHideT);if(!pvPinned)pvHideT=setTimeout(hidePv,260)}
pv.addEventListener("mouseenter",()=>clearTimeout(pvHideT));pv.addEventListener("mouseleave",()=>{if(!pvPinned)hidePv()});
function stmtPv(id){const e=BYID[id];if(!e)return null;const r=REFS[e.label]||{};
  return `<div class="pk">${(r.abbr||abbrOf(e.kind))} ${r.num||''}</div><div class="pt">${detex(e.title)}</div><div>${proseHtml(e.body).slice(0,1200)}</div>`}
function leanPv(name){const code=LEANCODE[name];return code?`<div class="pk">Lean · ${esc(name)}</div><pre class="lean">${leanHi(code)}</pre>`:null}
function graphPv(id){const e=BYID[id];if(!e)return null;return `<div class="pv-graphwrap"><div class="pk">Local dependencies</div>${depGraph(e)}</div>`}
function leanTagPv(id){const e=BYID[id];if(!e)return null;
  if(e.lean&&e.lean.length)return e.lean.map(l=>`<div class="pk">Lean · ${esc(l.name)}${l.status?' · '+l.status.replace('_',' '):''}</div>${l.code?`<pre class="lean">${leanHi(l.code)}</pre>`:''}`).join("");
  if(e.mathlib_name)return `<div class="pk">Mathlib</div><div style="margin-top:4px">${esc([].concat(e.mathlib_name).join(', '))}</div>`;return null}
function citePv(key){const b=BIB[key];
  if(!b)return `<div class="pk">Reference</div><div style="margin-top:4px;color:var(--muted)">Unknown reference <b>${esc(key)}</b> (no matching <code>.bib</code> entry).</div>`;
  return `<div class="pk">Reference [${b._n}]</div><div style="margin-top:5px;line-height:1.5">${fmtBib(b)}${b.url?` <a href="${esc(b.url)}" target="_blank" rel="noopener">↗</a>`:''}</div>`}
document.addEventListener("mouseover",ev=>{if(pvPinned)return;
  const d=ev.target.closest(".ref[data-id],.mm[data-goto],.hovprev[data-id]"),ln=ev.target.closest(".leanref"),ci=ev.target.closest(".cite[data-cite]");
  clearTimeout(pvHideT);
  if(ci){pvT=setTimeout(()=>showPv(citePv(ci.dataset.cite),ev.clientX,ev.clientY),110)}
  else if(d&&(d.dataset.id||d.dataset.goto)){pvT=setTimeout(()=>{const h=stmtPv(d.dataset.id||d.dataset.goto);if(h)showPv(h,ev.clientX,ev.clientY)},110)}
  else if(ln&&ln.dataset.name){pvT=setTimeout(()=>{const h=leanPv(ln.dataset.name);if(h)showPv(h,ev.clientX,ev.clientY)},110)}});
document.addEventListener("mouseout",ev=>{if(!pvPinned&&ev.target.closest(".ref,.gn,.leanref,.mm,.hovprev,.cite")){clearTimeout(pvT);schedHide()}});

/* ---- mini dependency graph (side panel / popups): same leanblueprint box style ---- */
const _GB={formalized:"#2e7d32",ready:"#1565c0",blocked:"#b0bec5"},_GF={done:"#66bb6a",local:"#c8e6c9",incomplete:"#ffcc80",ready:"#bbdefb",notready:"#eef1f4"};
function entryStyle(e){if(typeof GM!=="undefined"&&GM.built&&GM.idx[e.id]!=null){const n=GM.nodes[GM.idx[e.id]];return{b:_GB[n._stmt]||"#b0bec5",f:_GF[n._proof]||"#eef1f4"}}
  const ls=e.lean_status;return{b:ls==="empty"?"#b0bec5":"#2e7d32",f:ls==="mathlib_ok"?"#66bb6a":ls==="lean_ok"?"#c8e6c9":ls==="sorry"?"#ffcc80":"#eef1f4"}}
/* wrap a title to <=maxl lines of ~maxc chars, appending "…" only when text was
   actually dropped — the plainTex title (not "Def 3.4"), matching the big graph */
function _wrapTitle(t,maxc,maxl){const full=plainTex(t||"").trim();if(!full)return[""];
  const words=full.split(/\s+/),out=[];let cur="",i=0;
  while(i<words.length){const w=words[i],c=cur?cur+" "+w:w;
    if(c.length<=maxc||!cur){cur=c;i++}
    else{if(out.length===maxl-1)break;out.push(cur);cur=""}}
  if(cur&&out.length<maxl)out.push(cur);
  if(i<words.length){let last=out.length?out[out.length-1]:"";           /* truncated → ellipsis */
    while(last.length>maxc-1)last=last.slice(0,-1);
    out[out.length?out.length-1:0]=last.replace(/[ ,;:]+$/,"")+"…"}
  return out.slice(0,maxl)}
function depGraph(e){const CAP=5,MAXL=3;
  const ups=e.deps.map(d=>BYID[d.id]).filter(Boolean),downs=(REV[e.id]||[]).map(id=>BYID[id]).filter(Boolean);
  if(!ups.length&&!downs.length)return `<div class="ro">No dependency edges.</div>`;
  const u=ups.slice(0,CAP),dn=downs.slice(0,CAP),rows=[["uses ↑",u],["",[e]],["↓ used by",dn]];
  /* wrap every label first; size box height to the tallest so rows align and text fits */
  /* readable label — the human title (LaTeX flattened to text), then a de-prefixed
     label, never the raw hash id. */
  const _dlabel=nd=>{const t=plainTex(nd.title||"");if(t)return t;
    const l=(nd.label||"").replace(/^[a-z]+:/,"").replace(/[-_]/g," ").trim();return l||nd.kind||"node"};
  const lab=new Map();[...u,e,...dn].forEach(nd=>lab.set(nd,_wrapTitle(_dlabel(nd),22,MAXL)));
  const maxLines=Math.max(1,...[...lab.values()].map(l=>l.length));
  const per=Math.max(u.length,dn.length,1),BW=156,BH=14+maxLines*13,W=Math.max(516,per*(BW+18)+84),rowH=BH+30,pad=16,cx=W/2;
  const H=pad*2+rowH*3;const yOf=i=>pad+rowH*i+rowH/2;let boxes="",lines="";
  rows.forEach((r,i)=>{const n=r[1].length;r[1].forEach((nd,j)=>{const x=80+(W-92)/(n+1)*(j+1),y=yOf(i);nd._x=x;nd._y=y;const me=i===1;
    const tl=lab.get(nd);
    const st=entryStyle(nd),def=_defKind(nd.kind),w=BW;
    const shape=def?`<rect width="${w}" height="${BH}" rx="7" fill="${me?'#eef1ff':st.f}" stroke="${me?'#4f46e5':st.b}" stroke-width="${me?2.4:2}"/>`
      :`<ellipse cx="${w/2}" cy="${BH/2}" rx="${w/2}" ry="${BH/2}" fill="${me?'#eef1ff':st.f}" stroke="${me?'#4f46e5':st.b}" stroke-width="${me?2.4:2}"/>`;
    const y0=BH/2-(tl.length-1)*6.5+3.5,txt=tl.map((ln,k)=>`<tspan x="${w/2}" ${k?'dy="13"':''}>${esc(ln)}</tspan>`).join("");
    boxes+=`<g class="gn" ${me?'':'data-id="'+nd.id+'"'} transform="translate(${x-w/2},${y-BH/2})">${shape}<text x="${w/2}" y="${y0}" text-anchor="middle" fill="#1c2024" font-size="11">${txt}</text></g>`})});
  const curve=(x1,y1,x2,y2)=>{const my=(y1+y2)/2;return `<path d="M${x1} ${y1} C${x1} ${my.toFixed(1)} ${x2} ${my.toFixed(1)} ${x2} ${y2}" fill="none" stroke="#c1c6d0" stroke-width="1.4" marker-end="url(#ah)"/>`};
  u.forEach(nd=>lines+=curve(nd._x,nd._y+BH/2,cx,yOf(1)-BH/2));
  dn.forEach(nd=>lines+=curve(cx,yOf(1)+BH/2,nd._x,nd._y-BH/2));
  const rlab=rows.map((r,i)=>r[0]?`<text x="8" y="${yOf(i)+4}" fill="#6b7280" font-size="10">${r[0]}</text>`:"").join("");
  const more=(ups.length>CAP?`<div class="ro">+${ups.length-CAP} more used ↑. </div>`:"")+(downs.length>CAP?`<div class="ro">+${downs.length-CAP} more use this.</div>`:"");
  const hint=(typeof GM!=="undefined")?`<div class="ro" style="background:none;padding:4px 2px 0">click a node to open it in the graph</div>`:"";
  return `<div class="gwrap"><svg class="graph" viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet" style="height:auto;max-height:480px;display:block"><defs><marker id="ah" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 z" fill="#c1c6d0"/></marker></defs>${rlab}${lines}${boxes}</svg></div>${more}${hint}`;
}

/* node detail — rendered into the graph's persistent side panel */
function nodePanel(e){if(!e)return `<div class="gp-empty">Select a node to see its statement, Lean &amp; dependencies.</div>`;
  const r=REFS[e.label]||{};
  const lean=e.lean.map(l=>`<div style="margin-bottom:8px"><code>${esc(l.name)}</code> ${sb(l.status)}${l.code?`<pre class="lean">${leanHi(l.code)}</pre>`:''}</div>`).join("");
  return `<button class="gp-close" onclick="gmSelect(null)" title="Close (Esc)" aria-label="Close panel">&#10005;</button><div class="gp-h"><div class="gp-k">${(r.abbr||abbrOf(e.kind))} ${r.num||''}</div>
      <div class="gp-t st">${detex(e.title)}</div><div style="margin-top:6px">${sb(e.lean_status)}</div></div>
    <div class="gp-c"><div class="sbody">${proseHtml(e.body)}</div>
      ${lean?`<h3>Lean</h3>${lean}`:(e.mathlib_name?`<h3>Mathlib</h3><code>${esc([].concat(e.mathlib_name).join(', '))}</code>`:"")}
      <h3>Dependencies</h3>${depGraph(e)}</div>`}
function renderOverview(){curView="overview";clearControls();setNav("ovbtn");const main=document.getElementById("main");main.classList.remove("results");
  const col={mathlib_ok:'#0b5fd0',lean_ok:'#137333',sorry:'#d11a2a',empty:'#9aa2ad'};
  const sw=c=>`<i class="sw" style="background:${c}"></i>`;
  /* title page (\maketitle) */
  const maketitle=`<div class="maketitle"><h1>${detex(DATA.docTitle||DATA.title||"Blueprint")}</h1>${DATA.docAuthor?`<div class="mkauthor">${detex(DATA.docAuthor)}</div>`:''}</div>`;
  const legend=`<div class="ovleg">
    <span>${sw('#0b5fd0')}mathlib</span><span>${sw('#137333')}lean ok</span>
    <span>${sw('#d11a2a')}sorry</span><span>${sw('#9aa2ad')}no lean</span></div>`;
  /* full contents: chapters → sections → subsections, progressively disclosed.
     The squares never turn into a percentage — they just re-partition one level
     finer each time you expand: collapsed, a chapter shows every one of its
     statements flattened into one row; expand it and those same squares split
     out per section; expand a section (if it has subsections) and its squares
     split again per subsection. Collapsing re-flattens, nothing is ever hidden
     behind a number. */
  const sqOf=stmts=>stmts.map(b=>{const st=b.enrich?b.enrich.lean_status:'empty';
    return `<i class="mm" style="background:${col[st]}" data-goto="${b.id||''}"></i>`}).join("");
  const secLabel=r=>r.num?`<div class="co-sec"><span class="n">${esc(r.num)}</span>${detex(r.title)}</div>`
    :`<span class="co-sec" style="color:var(--muted)">Introduction</span>`;
  const body=(DATA.chapters||[]).map((ch,i)=>{const secs=chapterTree(ch);if(!secs.length)return"";
    const chStmts=secs.flatMap(s=>s.stmts.concat(s.subs.flatMap(u=>u.stmts)));
    if(!chStmts.length)return"";
    const secsHtml=secs.map(s=>{
      /* a section's own statements before its first subsection heading don't
         belong to any subsection — give them their own (unlabeled) row so
         expanding the section doesn't make them disappear */
      const directHtml=s.stmts.length?`<div class="ov-subsection"><span class="co-sec" style="color:var(--muted)">Direct</span><div class="mmcells ov-statements">${sqOf(s.stmts)}</div></div>`:'';
      const subsHtml=directHtml+s.subs.map(u=>`<div class="ov-subsection"><div class="co-sec"><span class="n">${esc(u.num)}</span>${detex(u.title)}</div><div class="mmcells ov-statements">${sqOf(u.stmts)}</div></div>`).join("");
      const secStmts=s.stmts.concat(s.subs.flatMap(u=>u.stmts));
      if(!s.subs.length)     /* leaf section: nothing finer to drill into, just show its squares */
        return `<div class="ov-section-h">${secLabel(s)}<div class="mmcells ov-statements">${sqOf(secStmts)}</div></div>`;
      /* has subsections: collapsed → all its squares flattened (shown inside the
         summary itself, so they're visible while closed too); expanded → the
         summary's flat row hides (see CSS) and per-subsection rows take over. */
      return `<details class="ov-section"><summary>${secLabel(s)}<div class="mmcells ov-statements ov-flat">${sqOf(secStmts)}</div></summary><div class="ov-subsections">${subsHtml}</div></details>`;
    }).join("");
    return `<details class="ov-chapter"><summary><div class="ov-chh"><span class="hn">${ch.num}</span>${detex(ch.title)}</div><div class="mmcells ov-statements ov-flat">${sqOf(chStmts)}</div></summary><div class="ov-sections">${secsHtml}</div></details>`;}).join("");
  main.innerHTML=maketitle+`<div class="ovleg-wrap">${legend}</div>`+body;typesetLazy(main);window.scrollTo(0,0);renderOutline();}
document.addEventListener("keydown",e=>{if(e.key==="Escape"){if(pvPinned){hidePv();return}pv.style.display="none";
  if(GM.open){if(GM.sel!=null){gmSelect(null);return}closeGraph()}}});

/* ---- navigate to a statement in its chapter ---- */
function navigate(id){const ci=LOC[id];pv.style.display="none";
  if(ci==null)return;
  document.getElementById("q").value="";active.clear();document.querySelectorAll(".chip.on").forEach(c=>c.classList.remove("on"));
  renderChapter(ci);
  setHash(BYID[id]&&BYID[id].label?BYID[id].label:id);
  requestAnimationFrame(()=>{const el=document.getElementById("stmt-"+id);if(el){el.scrollIntoView({block:"center"});el.classList.add("flash");setTimeout(()=>el.classList.remove("flash"),1700)}});}

/* ---- deep-linking: keep the URL #hash in sync and honour incoming hashes ----
   External links (e.g. a proof-structure diagram) can point at
     dashboard.html#thm:bishop-gromov   (a statement, by its \label or id)
     dashboard.html#ch-2                 (a chapter, 1-based)
   HASHNAV guards the replaceState we do ourselves from re-triggering routing. */
let HASHNAV=false;
function setHash(frag){HASHNAV=true;try{history.replaceState(null,"","#"+encodeURIComponent(frag))}catch(e){location.hash=frag}
  requestAnimationFrame(()=>{HASHNAV=false})}
function gotoHash(){let h=location.hash.replace(/^#/,"");if(!h)return false;
  try{h=decodeURIComponent(h)}catch(e){}
  let m=h.match(/^(?:ch|chapter)-(\d+)$/i);
  if(m){const i=(+m[1])-1;if(DATA.chapters&&DATA.chapters[i]){renderChapter(i);return true}return false}
  if(h.startsWith("stmt-"))h=h.slice(5);
  const id=BYID[h]?h:(BYLBL[h]||null);
  if(id!=null){navigate(id);return true}
  return false}

/* ================= full dependency graph ================= */
const GCOL={mathlib_ok:"#0b5fd0",lean_ok:"#137333",sorry:"#d11a2a",empty:"#9aa2ad"};
/* Chapters are the only clustering axis. Every chapter starts collapsed into one
   purple aggregate box; clicking it expands it in place — its declarations appear
   in a purple-bordered cluster, every OTHER chapter stays visible as its own
   collapsed box (nothing is ever fully replaced/lost). Collapsing (click the
   cluster background) or changing the detail level always regenerates a fresh DOT
   graph and re-renders it — a real Graphviz re-layout, not hide/show on a stale
   one. "layered" is the offline canvas fallback (only used if Graphviz/dot is
   unavailable at all — no CDN, no `dot` binary). */
const _LVL={coarse:0,medium:1,fine:2};   /* granularity → numeric rank (0=coarsest) */
const GM={open:false,inited:false,built:false,nodes:[],edges:[],adj:[],idx:{},chaps:[],
  layout:"mixed",expanded:new Set(),targets:{},passArr:[],visArr:[],lvlMax:2,gf:new Set(),q:"",autofit:false,
  scale:1,tx:0,ty:0,dpr:1,alpha:0,raf:null,dirty:false,drag:null,down:null,hover:null,hovset:null,sel:null,
  busy:false,canvas:null,ctx:null,
  gvLoading:null,gvGraphviz:null,gvRendered:false,gvSelEl:null,gvRaf:null};

function gmBuild(){if(GM.built)return;GM.built=true;
  const ents=DATA.entries;const idx={};ents.forEach((e,i)=>idx[e.id]=i);
  GM.nodes=ents.map((e,i)=>({id:e.id,e,i,x:0,y:0,vx:0,vy:0,fx:0,fy:0,r:5,ind:0,rank:0,ch:0,
    lvl:(_LVL[e.level]!=null?_LVL[e.level]:2)}));
  const seen=new Set();GM.edges=[];
  ents.forEach(e=>{const s=idx[e.id];(e.deps||[]).forEach(d=>{const t=idx[d.id];if(t==null||t===s)return;
    const k=s+"_"+t;if(seen.has(k))return;seen.add(k);GM.edges.push([s,t,d.type||"depends_on"]);GM.nodes[t].ind++})});
  GM.nodes.forEach(n=>n.r=4+Math.sqrt(n.ind)*2.1);
  GM.idx=idx;GM.adj=GM.nodes.map(()=>[]);
  GM.edges.forEach(([s,t])=>{GM.adj[s].push(t);GM.adj[t].push(s)});
  gmRanks();gmChapters();gmStatuses();gmComputePass();
}
/* per-node statement status (border) + proof status (fill), leanblueprint-style */
function gmStatuses(){const N=GM.nodes,F=e=>e.lean_status==="lean_ok"||e.lean_status==="mathlib_ok";
  const deps=N.map(()=>[]);GM.edges.forEach(([s,t])=>deps[s].push(t));       /* s uses t */
  const cm={},cst={};function closed(i){if(cm[i]!==undefined)return cm[i];if(cst[i])return F(N[i].e);
    cst[i]=1;let r=F(N[i].e);if(r)for(const t of deps[i]){if(!closed(t)){r=false;break}}cst[i]=0;return cm[i]=r}
  N.forEach(n=>{const e=n.e,f=F(e),D=deps[n.i];n._closed=closed(n.i);
    const allLean=D.every(t=>N[t].e.lean_status!=="empty"),allF=D.every(t=>F(N[t].e));
    n._stmt=e.lean_status!=="empty"?"formalized":(D.length===0||allLean?"ready":"blocked");
    n._proof=n._closed?"done":f?"local":e.lean_status==="sorry"?"incomplete":(e.lean_status==="empty"&&(D.length===0||allF)?"ready":"notready")})}
const GBORDER={formalized:"#2e7d32",ready:"#1565c0",blocked:"#b0bec5"};
const GFILL={done:"#66bb6a",local:"#c8e6c9",incomplete:"#ffcc80",ready:"#bbdefb",notready:"#eef1f4"};
function gmStyle(n){return{b:GBORDER[n._stmt]||"#b0bec5",f:GFILL[n._proof]||"#eef1f4"}}
function gmRanks(){const N=GM.nodes,st=new Int8Array(N.length),rank=new Int32Array(N.length);
  const deps=N.map(()=>[]);GM.edges.forEach(([s,t])=>deps[s].push(t));   // s uses t
  const visit=i=>{if(st[i]===2)return rank[i];if(st[i]===1)return 0;st[i]=1;let r=0;
    const dl=deps[i];for(let k=0;k<dl.length;k++)r=Math.max(r,visit(dl[k])+1);st[i]=2;rank[i]=r;return r};
  for(let i=0;i<N.length;i++)visit(i);N.forEach(n=>n.rank=rank[n.i]);
}
function gmChapters(){const keyOf=n=>(LOC&&LOC[n.id]!=null)?LOC[n.id]:(n.e.chapter||"·");
  const order=[],seen={};GM.nodes.forEach(n=>{const k=keyOf(n);if(!(k in seen)){seen[k]=order.length;order.push(k)}n.ch=seen[k]});
  const label=k=>{if(DATA.chapters&&DATA.chapters[k])return (DATA.chapters[k].num||"")+" "+plainTex(DATA.chapters[k].title);
    return plainTex(String(k)).slice(0,30)};
  const K=order.length,R=Math.max(520,K*66);
  GM.chaps=order.map((k,i)=>{const a=(i/Math.max(1,K))*Math.PI*2-Math.PI/2;
    return {key:k,label:label(k),cx:Math.cos(a)*R,cy:Math.sin(a)*R,n:0}});
  GM.nodes.forEach(n=>{GM.chaps[n.ch]&&GM.chaps[n.ch].n++});
}
/* ---- analytic layouts ---- */
/* Sugiyama layered DAG: rank by depth, median crossing-reduction sweeps, then a
   barycenter x-pass with overlap resolution → a clean top→bottom, non-overlapping graph. */
function gmSugiyama(){const byR={};let maxr=0;GM.nodes.forEach(n=>{(byR[n.rank]=byR[n.rank]||[]).push(n);if(n.rank>maxr)maxr=n.rank});
  const layers=[];for(let r=0;r<=maxr;r++)layers[r]=byR[r]||[];
  const upN=GM.nodes.map(()=>[]),downN=GM.nodes.map(()=>[]);
  GM.edges.forEach(([s,t])=>{upN[s].push(t);downN[t].push(s)});
  layers.forEach(L=>L.sort((a,b)=>a.i-b.i));
  const pos=new Float64Array(GM.nodes.length);const setpos=()=>layers.forEach(L=>L.forEach((n,i)=>pos[n.i]=i));setpos();
  const med=arr=>{if(!arr.length)return -1;const s=arr.map(i=>pos[i]).sort((a,b)=>a-b);const m=s.length>>1;return s.length%2?s[m]:(s[m-1]+s[m])/2};
  for(let sw=0;sw<6;sw++){const down=sw%2===0;
    if(down){for(let r=1;r<=maxr;r++){layers[r].forEach(n=>n._m=med(upN[n.i]));layers[r].sort((a,b)=>(a._m<0?pos[a.i]:a._m)-(b._m<0?pos[b.i]:b._m))}}
    else{for(let r=maxr-1;r>=0;r--){layers[r].forEach(n=>n._m=med(downN[n.i]));layers[r].sort((a,b)=>(a._m<0?pos[a.i]:a._m)-(b._m<0?pos[b.i]:b._m))}}
    setpos()}
  const GXX=FBW+26,GYY=FBH+66,t={};
  layers.forEach((L,r)=>{const w=(L.length-1)*GXX;L.forEach((n,i)=>t[n.i]={x:i*GXX-w/2,y:r*GYY})});
  for(let pass=0;pass<4;pass++)layers.forEach(L=>{L.forEach(n=>{const nb=upN[n.i].concat(downN[n.i]);if(nb.length){let sx=0;for(const m of nb)sx+=t[m].x;t[n.i].x=sx/nb.length}});
    L.sort((a,b)=>t[a.i].x-t[b.i].x);for(let i=1;i<L.length;i++)if(t[L[i].i].x-t[L[i-1].i].x<GXX)t[L[i].i].x=t[L[i-1].i].x+GXX});
  return t}
/* ---- per-chapter aggregate stats (count/done) + inter-chapter edge weights —
   used by gmDotMixed() to build the collapsed chapter boxes and their edges ---- */
function gmBuildGroups(){if(GM.gdata)return GM.gdata;const K=GM.chaps.length;
  const stat=GM.chaps.map((c,i)=>({ch:i,count:0,done:0}));
  GM.nodes.forEach(n=>{stat[n.ch].count++;if(n._closed||n._F)stat[n.ch].done++});
  const em={};for(const[s,t]of GM.edges){const a=GM.nodes[s].ch,b=GM.nodes[t].ch;if(a===b)continue;const k=b+"_"+a;em[k]=(em[k]||0)+1}
  GM.gdata={stat,edges:Object.keys(em).map(k=>{const p=k.split("_");return[+p[0],+p[1],em[k]]})};return GM.gdata}
function gmWrapText(ctx,text,maxw,maxlines){const words=text.split(/\s+/),out=[];let cur="";
  for(const w of words){const t=cur?cur+" "+w:w;if(ctx.measureText(t).width<=maxw||!cur)cur=t;else{out.push(cur);cur=w;if(out.length>=maxlines-1)break}}
  if(cur&&out.length<maxlines)out.push(cur);if(out.length>=maxlines){let s=out[maxlines-1];while(s.length&&ctx.measureText(s+"…").width>maxw)s=s.slice(0,-1);out[maxlines-1]=s+"…"}return out.slice(0,maxlines)}
function _defKind(k){return k==="definition"||k==="example"||k==="remark"||k==="notation"||k==="convention"}

/* ---- per-chapter focus: leanblueprint-style labelled boxes, top→bottom by depth,
   other chapters collapsed into group nodes when cross-chapter deps exist ---- */
const FBW=172,FBH=54;
function gmChapLabel(ch){const c=GM.chaps[ch];return c?c.label:("chapter "+ch)}
/* wrap a node's title to <=2 lines that fit the box; cached on the node */
function gmLines(ctx,n){if(n._lines)return n._lines;ctx.font="13px -apple-system,Segoe UI,Roboto,sans-serif";
  const words=plainTex(n.e.title||n.e.label||n.e.id).split(/\s+/),maxw=FBW-20,out=[];let cur="";
  for(const w of words){const t=cur?cur+" "+w:w;if(ctx.measureText(t).width<=maxw||!cur)cur=t;else{out.push(cur);cur=w;if(out.length>=1)break}}
  if(cur&&out.length<2)out.push(cur);
  if(out.length>=2){let s=out[1];while(s.length&&ctx.measureText(s+"…").width>maxw)s=s.slice(0,-1);out[1]=s+"…"}
  else if(out.length===1&&ctx.measureText(out[0]).width>maxw){let s=out[0];while(s.length&&ctx.measureText(s+"…").width>maxw)s=s.slice(0,-1);out[0]=s+"…"}
  return n._lines=out}
/* draw one node as a leanblueprint box (rect=def, ellipse=thm) with two-tone
   colour and world-space title text — used by every graph view */
function gmBoxNode(ctx,n,z){const def=_defKind(n.e.kind),st=gmStyle(n),x=n.x-FBW/2,y=n.y-FBH/2;
  ctx.fillStyle=st.f;ctx.strokeStyle=st.b;ctx.lineWidth=Math.max(1,2.2/z);
  if(def){_rr(ctx,x,y,FBW,FBH,6)}else{ctx.beginPath();ctx.ellipse(n.x,n.y,FBW/2,FBH/2,0,0,6.2832)}
  ctx.fill();ctx.stroke();
  if(GM.sel===n.i){ctx.strokeStyle="#4f46e5";ctx.lineWidth=3.4/z;if(def)_rr(ctx,x-3.5,y-3.5,FBW+7,FBH+7,8);else{ctx.beginPath();ctx.ellipse(n.x,n.y,FBW/2+3.5,FBH/2+3.5,0,0,6.2832)}ctx.stroke()}}
/* labels in SCREEN space — a constant font that does not scale with zoom, wrapped
   to fit the box's on-screen width; hidden when the box is too small to hold text */
function gmBoxLabels(ctx,r,z,nodes){if(GM.busy||FBW*z<52)return;
  const filt=GM.gf.size||GM.q,pass=GM.passArr,bw=FBW*z-14;
  ctx.textAlign="center";ctx.textBaseline="middle";ctx.font="12px -apple-system,Segoe UI,Roboto,sans-serif";ctx.fillStyle="#1c2024";
  for(const n of nodes){if(GM.visArr&&!GM.visArr[n.i])continue;if(filt&&!pass[n.i])continue;const sx=n.x*z+GM.tx,sy=n.y*z+GM.ty;
    if(sx<-110||sy<-50||sx>r.width+110||sy>r.height+50)continue;
    const ls=gmWrapText(ctx,plainTex(n.e.title||n.e.label||n.e.id),bw,2),y0=sy-(ls.length-1)*7.5;
    ls.forEach((l,i)=>ctx.fillText(l,sx,y0+i*15))}}
/* one edge as a curved bezier with an arrowhead near the target box */
function gmEdge(ctx,a,b,z,dashed,arrow){const dx=b.x-a.x,dy=(b.y-FBH/2)-(a.y+FBH/2);
  const ay=a.y+FBH/2,by=b.y-FBH/2,mx=(a.x+b.x)/2,my=(ay+by)/2,cx=mx+dx*0.06,cy=my;
  ctx.setLineDash(dashed?[4/z,4/z]:[]);ctx.beginPath();ctx.moveTo(a.x,ay);ctx.quadraticCurveTo(cx,cy,b.x,by);ctx.stroke();ctx.setLineDash([]);
  if(arrow){const ang=Math.atan2(by-cy,b.x-cx),ah=7/z;ctx.beginPath();ctx.moveTo(b.x,by);
    ctx.lineTo(b.x-Math.cos(ang-0.42)*ah,by-Math.sin(ang-0.42)*ah);ctx.lineTo(b.x-Math.cos(ang+0.42)*ah,by-Math.sin(ang+0.42)*ah);ctx.closePath();ctx.fill()}}
function _rr(ctx,x,y,w,h,r){ctx.beginPath();ctx.moveTo(x+r,y);ctx.arcTo(x+w,y,x+w,y+h,r);ctx.arcTo(x+w,y+h,x,y+h,r);ctx.arcTo(x,y+h,x,y,r);ctx.arcTo(x,y,x+w,y,r);ctx.closePath()}
/* draw the selected node's edges: OUT (its deps) blue, IN (used-by) orange */
function gmSelEdges(ctx,z,edges,idxOf){if(GM.sel==null)return;const si=GM.sel;
  for(const e of edges){const s=idxOf?idxOf(e,0):e[0],t=idxOf?idxOf(e,1):e[1];if(s!==si&&t!==si)continue;
    if(GM.visArr&&(!GM.visArr[s]||!GM.visArr[t]))continue;
    const a=GM.nodes[t],b=GM.nodes[s],out=(s===si),col=out?"#1d4ed8":"#c2410c";
    ctx.strokeStyle=col;ctx.fillStyle=col;ctx.lineWidth=Math.max(1.4,2.4/z);gmEdge(ctx,a,b,z,e[2]==="uses",true)}}
/* full leanblueprint-style DAG: every node a named box, border=statement, fill=proof */
function gmDrawDAG(){const cv=GM.canvas,ctx=GM.ctx,dpr=GM.dpr,r=cv.getBoundingClientRect(),z=GM.scale;
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,r.width,r.height);
  const N=GM.nodes,filt=GM.gf.size||GM.q,pass=GM.passArr,arrow=z>0.22;
  ctx.save();ctx.translate(GM.tx,GM.ty);ctx.scale(z,z);ctx.lineWidth=Math.max(.4,0.8/z);
  for(const[s,t,ty]of GM.edges){if(GM.sel===s||GM.sel===t)continue;if(GM.visArr&&(!GM.visArr[s]||!GM.visArr[t]))continue;const a=N[t],b=N[s],al=filt?((pass[s]&&pass[t])?0.42:0.03):0.3;
    ctx.strokeStyle="rgba(110,120,135,"+al+")";ctx.fillStyle="rgba(110,120,135,"+al+")";gmEdge(ctx,a,b,z,ty==="uses",arrow)}
  gmSelEdges(ctx,z,GM.edges);
  for(const n of N){if(GM.visArr&&!GM.visArr[n.i])continue;ctx.globalAlpha=(filt&&!pass[n.i])?0.12:1;gmBoxNode(ctx,n,z)}
  ctx.globalAlpha=1;ctx.restore();
  ctx.setTransform(dpr,0,0,dpr,0,0);gmBoxLabels(ctx,r,z,N);}

/* ---- filters ---- */
function gmComputePass(){const q=GM.q.toLowerCase(),sf=[...GM.gf].filter(f=>S.includes(f));
  GM.passArr=GM.nodes.map(n=>{const e=n.e;if(sf.length&&!sf.includes(e.lean_status))return false;
    if(q&&!((e.title+" "+(e.label||"")).toLowerCase().includes(q)))return false;return true});
  GM.visArr=GM.nodes.map(n=>n.lvl<=GM.lvlMax);   /* level-of-detail: hide finer-than-lvlMax */
  const c=document.getElementById("gmCount");if(c){const tot=GM.nodes.length,
    vis=GM.visArr.filter(Boolean).length,on=GM.passArr.filter((p,i)=>p&&GM.visArr[i]).length;
    c.innerHTML=(GM.gf.size||GM.q)?`<b>${on}</b> of ${tot} nodes`
      :(GM.lvlMax<2?`<b>${vis}</b> of ${tot} nodes · ${["coarse","coarse+medium"][GM.lvlMax]}`:`<b>${tot}</b> nodes · ${GM.edges.length} edges`)}
  if(gmSvgMode()&&GM.gvRendered)gmGvizApplyFilter();}

/* ---- view transform helpers ---- */
function gmS2W(cx,cy){const r=GM.canvas.getBoundingClientRect();return {x:(cx-r.left-GM.tx)/GM.scale,y:(cy-r.top-GM.ty)/GM.scale}}
function gmHit(wx,wy){const N=GM.nodes;for(let k=N.length-1;k>=0;k--){const n=N[k];if(Math.abs(n.x-wx)<=FBW/2&&Math.abs(n.y-wy)<=FBH/2)return n}return null}
function gmZoom(cx,cy,f){const r=GM.canvas.getBoundingClientRect(),mx=cx-r.left,my=cy-r.top;
  const wx=(mx-GM.tx)/GM.scale,wy=(my-GM.ty)/GM.scale;GM.scale=Math.max(.02,Math.min(4,GM.scale*f));
  GM.tx=mx-wx*GM.scale;GM.ty=my-wy*GM.scale;gmKick()}
function gmResize(){const cv=GM.canvas;if(!cv)return;const r=cv.getBoundingClientRect(),dpr=window.devicePixelRatio||1;
  cv.width=Math.max(1,r.width*dpr);cv.height=Math.max(1,r.height*dpr);GM.dpr=dpr;gmKick()}
/* everything below is the offline canvas fallback: only reached when Graphviz
   (precomputed SVG + the WASM CDN) is entirely unavailable */
function gmFit(){if(gmSvgMode()){gmGvizFit();return}
  let a=1e9,b=1e9,c=-1e9,d=-1e9;const pts=[];
  for(const n of GM.nodes)pts.push([n.x-FBW/2,n.y-FBH/2],[n.x+FBW/2,n.y+FBH/2]);
  for(const[x,y]of pts){if(!isFinite(x)||!isFinite(y))continue;if(x<a)a=x;if(y<b)b=y;if(x>c)c=x;if(y>d)d=y}
  if(a>c||!isFinite(a)||!isFinite(c))return;const r=GM.canvas.getBoundingClientRect(),pad=80;
  GM.scale=Math.max(.02,Math.min(1.6,Math.min((r.width-pad*2)/Math.max(1,c-a),(r.height-pad*2)/Math.max(1,d-b))));
  GM.tx=r.width/2-(a+c)/2*GM.scale;GM.ty=r.height/2-(b+d)/2*GM.scale}
function gmCenterOn(n){if(!n||!GM.canvas)return;const r=GM.canvas.getBoundingClientRect();GM.autofit=false;
  if(GM.scale<0.6)GM.scale=0.85;GM.tx=r.width/2-n.x*GM.scale;GM.ty=r.height/2-n.y*GM.scale;gmKick()}
/* select a node and pan the main graph to it (from a mini dep-graph click) —
   expands its chapter first if that's not already showing its declarations */
function gmGoto(id){const nn=GM.nodes[GM.idx[id]];if(!nn)return;
  if(!gmSvgMode()){GM.sel=nn.i;gmSelect(nn);requestAnimationFrame(()=>gmCenterOn(nn));return}
  GM.sel=nn.i;
  const side=document.getElementById("gm-side");if(side){side.innerHTML=nodePanel(nn.e);typeset(side)}
  const needExpand=!GM.expanded.has(nn.ch);
  if(needExpand)GM.expanded.add(nn.ch);
  if(needExpand||!GM.gvRendered){GM._gvAfter=()=>{gmGvizSelect();gmGvizCenterOn(id)};gmRenderGviz()}
  else{gmGvizSelect();gmGvizCenterOn(id)}}

/* ---- render ---- */
function gmLabel(n){const t=plainTex(n.e.title||"")||((n.e.label||"").replace(/^[a-z]+:/,""))||n.e.id;return t.length>30?t.slice(0,29)+"…":t}
function gmDraw(){const cv=GM.canvas,ctx=GM.ctx;if(!cv)return;
  if(gmSvgMode())return;   /* SVG-rendered by Graphviz, not on canvas */
  return gmDrawDAG();}
function gmKick(){if(gmSvgMode())return;   /* Graphviz view is static SVG; no canvas RAF */
  GM.dirty=true;if(!GM.raf&&GM.open)GM.raf=requestAnimationFrame(gmLoop)}
function gmLoop(){GM.raf=null;if(!GM.open)return;let cont=false;
  let mv=false;for(const n of GM.nodes){const t=GM.targets[n.i];if(!t)continue;const dx=t.x-n.x,dy=t.y-n.y;n.x+=dx*0.5;n.y+=dy*0.5;if(dx*dx+dy*dy>1)mv=true}if(mv)cont=true;
  GM.busy=cont;if(GM.autofit){gmFit();if(!cont)GM.autofit=false}
  gmDraw();if(cont||GM.dirty){GM.dirty=false;GM.raf=requestAnimationFrame(gmLoop)}}
/* ================= Graphviz (clustered SVG) layout — FLT-blueprint style =================
   Renders the same node/edge model as a Graphviz DOT graph with one `subgraph cluster`
   per chapter, laid out by Graphviz (d3-graphviz + WASM, loaded from a CDN). Falls back
   to the canvas "Layered" view when the libraries can't be fetched (offline export). */
const GV_D3="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js";
const GV_GRAPHVIZ="https://cdn.jsdelivr.net/npm/d3-graphviz@5.6.0/build/d3-graphviz.min.js";
function gvHave(){try{return !!(window.d3&&typeof window.d3.select==="function"&&typeof window.d3.select(document.createElement("div")).graphviz==="function")}catch(_){return false}}
function gmEnsureGviz(){if(GM.gvLoading)return GM.gvLoading;if(gvHave())return GM.gvLoading=Promise.resolve();
  const load=src=>new Promise((res,rej)=>{const s=document.createElement("script");s.src=src;s.onload=()=>res();s.onerror=()=>rej(new Error("failed to load "+src));document.head.appendChild(s)});
  GM.gvLoading=Promise.resolve()
    .then(()=>(window.d3&&window.d3.select)?null:load(GV_D3))
    .then(()=>gvHave()?null:load(GV_GRAPHVIZ))
    .then(()=>{if(!gvHave())throw new Error("d3-graphviz unavailable")})
    .catch(err=>{GM.gvLoading=null;throw err});
  return GM.gvLoading}
function gvEsc(s){return String(s).replace(/\\/g,"\\\\").replace(/"/g,'\\"')}
function gmDotLabel(n){const t=plainTex(n.e.title||n.e.label||n.e.id),words=t.split(/\s+/),lines=[];let cur="";const MAX=20;
  for(const w of words){const c=cur?cur+" "+w:w;if(c.length<=MAX||!cur)cur=c;else{lines.push(cur);cur=w;if(lines.length>=2)break}}
  if(cur&&lines.length<3)lines.push(cur);
  if(lines.length>=3&&lines[2].length>MAX)lines[2]=lines[2].slice(0,MAX-1)+"…";
  return lines.map(gvEsc).join("\\n")}
function gvLerp(a,b,t){return Math.round(a+(b-a)*t)}
function gvGreen(pct){const t=Math.max(0,Math.min(1,pct/100));
  return '#'+[[0xec,0x66],[0xf3,0xbb],[0xec,0x6a]].map(p=>gvLerp(p[0],p[1],t).toString(16).padStart(2,'0')).join('')}
/* The one graph: every chapter not in GM.expanded is a single purple aggregate
   box ("ch<N>", click → expand); every chapter IN GM.expanded is a real
   `subgraph cluster_<N>` (also purple-bordered, to read as "this is a chapter"
   rather than a declaration) containing its individual declaration nodes,
   filtered by the current detail level; click its background → collapse.
   Edges always resolve to whatever is CURRENTLY visible: a declaration in an
   expanded chapter keeps its own id, otherwise it collapses to its chapter's
   aggregate id — so nothing ever disappears, it just re-targets. Regenerated
   from scratch (a real Graphviz re-layout) on every expand/collapse/detail
   change, never just hidden on a stale layout. */
function gmDispId(n){
  if(GM.expanded.has(n.ch))return n.lvl<=GM.lvlMax?n.id:null;
  return 'ch'+n.ch;
}
function gmDotMixed(){const g=gmBuildGroups();
  const byCh={};GM.nodes.forEach(n=>{(byCh[n.ch]=byCh[n.ch]||[]).push(n)});
  let s='strict digraph "" {\n  rankdir=TB;bgcolor="transparent";pack=true;packmode="clust";splines=true;nodesep=0.4;ranksep=0.6;\n';
  s+='  node [shape=box,style="rounded,filled",fontname="Helvetica",fontsize=11,margin="0.11,0.05",penwidth=1.8];\n';
  s+='  edge [color="#8a93a0",arrowhead=vee,arrowsize=0.8,penwidth=1];\n';
  s+='  graph [fontname="Helvetica",fontsize=13,labeljust="l"];\n';
  g.stat.forEach((s0,ch)=>{if(!s0.count)return;
    if(GM.expanded.has(ch)){
      s+='  subgraph cluster_'+ch+' {\n    label="'+gvEsc(gmChapLabel(ch)+"  (click background to collapse)")+'";style="rounded,filled";fillcolor="#f3effc";color="#7c3aed";penwidth=2.4;fontcolor="#5b21b6";fontsize=12.5;\n';
      byCh[ch].filter(n=>n.lvl<=GM.lvlMax).forEach(n=>{const st=gmStyle(n),def=_defKind(n.e.kind);
        s+='    "'+n.id+'" [shape='+(def?"box":"ellipse")+',style='+(def?'"rounded,filled"':'"filled"')+',fillcolor="'+st.f+'",color="'+st.b+'",fontcolor="#1c2024",label="'+gmDotLabel(n)+'"];\n'});
      s+='  }\n';
    } else {
      const pct=Math.round(100*s0.done/s0.count);
      s+='  "ch'+ch+'" [label="'+gvEsc(gmChapLabel(ch))+'\\n'+s0.count+' statements · '+pct+'%",fillcolor="#ede9fe",color="#7c3aed",penwidth=2.6,fontcolor="#3b0a91",tooltip="'+gvEsc(gmChapLabel(ch))+' — click to expand"];\n';
    }});
  const seen=new Set();
  GM.edges.forEach(([si,ti,ty])=>{const sN=GM.nodes[si],tN=GM.nodes[ti];
    const sId=gmDispId(sN),tId=gmDispId(tN);
    if(sId==null||tId==null||sId===tId)return;
    const key=sId+" "+tId+" "+ty;if(seen.has(key))return;seen.add(key);
    s+='  "'+tId+'" -> "'+sId+'"'+(ty==="uses"?' [style=dashed]':'')+';\n'});
  return s+'}\n'}
/* which DOT to render; canvas is used only as the offline fallback */
function gmCurrentDot(){return gmDotMixed()}
function gmSvgMode(){return GM.layout!=="layered"}   /* "layered" is set only by the offline fallback */
function gvSvg(){const h=document.getElementById("gviz");return h?h.querySelector("svg"):null}
function gmShowGviz(on){const gv=document.getElementById("gviz");if(gv)gv.style.display=on?"block":"none";if(GM.canvas)GM.canvas.style.display=on?"none":"block"}
function gmGvizApplyFilter(){const svg=gvSvg();if(!svg)return;const filt=GM.gf.size||GM.q,pass=GM.passArr,vis=GM.visArr;
  svg.querySelectorAll("g.node").forEach(g=>{const i=GM.idx[g.dataset.nid];
    if(i!=null&&vis&&!vis[i]){g.style.display="none";return}g.style.display="";
    g.style.opacity=(filt&&i!=null&&!pass[i])?"0.12":"1"});
  svg.querySelectorAll("g.edge").forEach(g=>{const e=g.dataset.edge;if(!e)return;const p=e.split("->");if(p.length!==2)return;
    const a=GM.idx[p[0].trim()],b=GM.idx[p[1].trim()];
    if(vis&&((a!=null&&!vis[a])||(b!=null&&!vis[b]))){g.style.display="none";return}g.style.display="";
    g.style.opacity=(filt&&((a!=null&&!pass[a])||(b!=null&&!pass[b])))?"0.06":"1"})}
function gmGvizSelect(){const svg=gvSvg();if(!svg)return;
  if(GM.gvSelEl){GM.gvSelEl.forEach(o=>{o.el.setAttribute("stroke",o.s==null?"":o.s);if(o.w==null)o.el.removeAttribute("stroke-width");else o.el.setAttribute("stroke-width",o.w)});GM.gvSelEl=null}
  if(GM.sel==null)return;const id=GM.nodes[GM.sel].id;let node=null;
  svg.querySelectorAll("g.node").forEach(g=>{if(g.dataset.nid===id)node=g});
  if(!node)return;const store=[];node.querySelectorAll("polygon,ellipse,path").forEach(el=>{
    store.push({el,s:el.getAttribute("stroke"),w:el.getAttribute("stroke-width")});el.setAttribute("stroke","#4f46e5");el.setAttribute("stroke-width","3")});
  GM.gvSelEl=store}
function gmGvizPostRender(){const svg=gvSvg();if(!svg)return;GM.gvRendered=true;
  /* Move Graphviz's <title> (the raw id/hash) into a data attribute and delete it,
     so the browser's native tooltip stops showing hashes; hover uses stmtPv below. */
  svg.querySelectorAll("g.node").forEach(g=>{const t=g.querySelector("title"),id=t?t.textContent.trim():"";
    g.dataset.nid=id;if(t)t.remove();
    if(/^ch\d+$/.test(id)){g.style.cursor="pointer";g.addEventListener("click",ev=>{ev.stopPropagation();gmExpandChapter(+id.slice(2))});return}
    if(GM.idx[id]==null)return;
    g.style.cursor="pointer";
    g.addEventListener("click",ev=>{ev.stopPropagation();gmSelect(GM.nodes[GM.idx[id]])})});
  svg.querySelectorAll("g.edge").forEach(g=>{const t=g.querySelector("title");if(t){g.dataset.edge=t.textContent.trim();t.remove()}});
  /* an expanded chapter's cluster background (not a child node) → collapse it */
  svg.querySelectorAll("g.cluster").forEach(g=>{const t=g.querySelector("title"),id=t?t.textContent.trim():"";
    if(t)t.remove();const m=/^cluster_(\d+)$/.exec(id);if(!m)return;const ch=+m[1];
    g.style.cursor="pointer";
    g.addEventListener("click",ev=>{if(ev.target.closest("g.node"))return;ev.stopPropagation();gmCollapseChapter(ch)})});
  /* hover a real node → preview its statement (with rendered math); delegated so
     one listener covers every node and survives each re-render. */
  svg.addEventListener("mousemove",ev=>{if(pvPinned)return;const g=ev.target.closest("g.node");
    const id=g&&g.dataset.nid;
    if(!id||/^ch\d+$/.test(id)||GM.idx[id]==null){if(GM._gvHov!=null){GM._gvHov=null;clearTimeout(pvT);pv.style.display="none"}return}
    if(GM._gvHov===id)return;GM._gvHov=id;clearTimeout(pvT);const x=ev.clientX,y=ev.clientY;
    pvT=setTimeout(()=>{const h=stmtPv(id);if(h)showPv(h,x,y)},110)});
  svg.addEventListener("mouseleave",()=>{clearTimeout(pvT);GM._gvHov=null;if(!pvPinned)pv.style.display="none"});
  gmGvizApplyFilter();gmGvizSelect();
  const after=GM._gvAfter;GM._gvAfter=null;if(typeof after==="function")after()}
/* expand/collapse a chapter in place — every OTHER chapter stays exactly as it
   was (still its own collapsed box, or still expanded); only this one's
   membership in GM.expanded changes, then the whole mixed graph re-renders. */
function gmExpandChapter(ch){GM.expanded.add(ch);gmSelect(null);gmRenderGviz()}
function gmCollapseChapter(ch){GM.expanded.delete(ch);gmSelect(null);gmRenderGviz()}
function gmCollapseAll(){if(!GM.expanded.size)return;GM.expanded.clear();gmSelect(null);gmRenderGviz()}
/* pan/zoom the current SVG so a node is centred (used by the side-panel mini graphs) */
function gmGvizCenterOn(id){const gv=GM.gvGraphviz,svg=gvSvg();if(!svg)return;
  const node=[...svg.querySelectorAll("g.node")].find(g=>g.dataset.nid===id);
  if(!node)return;
  if(!gv){if(!GM.pz)return;const host=document.getElementById("gviz");const hr=host.getBoundingClientRect(),nr=node.getBoundingClientRect();
    GM.pz.x+=hr.width/2-(nr.left+nr.width/2-hr.left);GM.pz.y+=hr.height/2-(nr.top+nr.height/2-hr.top);GM.pzApply();return}
  if(!gv.zoomBehavior||!gv.zoomSelection)return;const zb=gv.zoomBehavior(),zs=gv.zoomSelection();if(!zb||!zs)return;const gnode=zs.node();
  try{const b=node.getBBox(),pt=svg.createSVGPoint();pt.x=b.x+b.width/2;pt.y=b.y+b.height/2;
    const m=gnode.getScreenCTM().inverse().multiply(node.getScreenCTM()),c=pt.matrixTransform(m);
    zb.translateTo(zs.transition().duration(450),c.x,c.y)}catch(_){}}
/* precomputed SVG (build-time `dot`) for the all-collapsed starting state only —
   instant, no CDN. The moment anything is expanded we need a fresh layout for
   that exact mix, which only the live WASM path can produce. */
function gmPreSvg(){if(!GVSVG||GM.expanded.size>0)return null;return GVSVG.groups||null}
/* Self-contained pan/zoom over Graphviz's root <g id="graph0" transform=…> — no
   CDN. host.innerHTML gets replaced on every re-render (expand/collapse/detail
   change), so the wheel/drag listeners (attached once) must never close over
   the svg/state from whichever render happened to be first — they read GM.pz
   and call gvSvg() fresh each time, so they keep working across any number of
   re-renders instead of silently operating on a detached, removed element. */
function gmZoomAt(mx,my,f){const s=GM.pz;if(!s)return;const nk=Math.max(0.05,Math.min(8,s.k*f)),sc=nk/s.k;
  s.x=mx-(mx-s.x)*sc;s.y=my-(my-s.y)*sc;s.k=nk;GM.pzApply()}
function gmPanZoom(host,svg){
  /* Size to the TRUE content bounds (getBBox), not the viewBox: d3-graphviz's
     fit(false) leaves a container-sized viewBox while the graph extends far
     beyond it, so overflow:hidden cropped everything but the top-left corner. */
  let bx=0,by=0,gw=0,gh=0;
  try{const bb=svg.getBBox();bx=bb.x;by=bb.y;gw=bb.width;gh=bb.height;}catch(_){}
  if(!(gw>0&&gh>0)){const vb=(svg.getAttribute("viewBox")||"").split(/\s+/).map(Number);
    bx=vb[0]||0;by=vb[1]||0;gw=vb[2]||1000;gh=vb[3]||1000;}
  const pad=24;bx-=pad;by-=pad;gw+=2*pad;gh+=2*pad;
  svg.setAttribute("viewBox",bx+" "+by+" "+gw+" "+gh);
  svg.removeAttribute("width");svg.removeAttribute("height");
  svg.style.position="absolute";svg.style.transformOrigin="0 0";svg.style.left="0";svg.style.top="0";
  svg.style.width=gw+"px";svg.style.height=gh+"px";svg.style.willChange="transform";
  const st={k:1,x:0,y:0,gw,gh};GM.pz=st;
  GM.pzApply=()=>{const s=gvSvg();if(s)s.style.transform="translate("+st.x.toFixed(1)+"px,"+st.y.toFixed(1)+"px) scale("+st.k+")"};
  GM.pzFit=()=>{const r=host.getBoundingClientRect();if(!r.width||!r.height)return;
    const k=Math.min(r.width/st.gw,r.height/st.gh)*0.92;
    st.k=k;st.x=(r.width-st.gw*k)/2;st.y=(r.height-st.gh*k)/2;GM.pzApply()};
  GM.pzFit();
  if(!host._pzWired){host._pzWired=true;
    /* trackpad two-finger swipe → PAN; pinch (ctrl+wheel) or mouse ctrl+wheel → ZOOM toward the cursor */
    host.addEventListener("wheel",e=>{e.preventDefault();const s=GM.pz;if(!s)return;
      const r=host.getBoundingClientRect();
      if(e.ctrlKey){gmZoomAt(e.clientX-r.left,e.clientY-r.top,Math.exp(-e.deltaY*0.01))}
      else{s.x-=e.deltaX;s.y-=e.deltaY;GM.pzApply()}},{passive:false});
    let drag=null;
    host.addEventListener("mousedown",e=>{if(e.button!==0||e.target.closest("g.node")||e.target.closest("g.cluster"))return;
      const s=GM.pz;if(!s)return;drag={x:e.clientX,y:e.clientY,ox:s.x,oy:s.y};host.style.cursor="grabbing";e.preventDefault()});
    window.addEventListener("mousemove",e=>{if(!drag)return;const s=GM.pz;if(!s)return;
      s.x=drag.ox+(e.clientX-drag.x);s.y=drag.oy+(e.clientY-drag.y);GM.pzApply()});
    window.addEventListener("mouseup",()=>{drag=null;host.style.cursor=""})}}
function gmCanvasFallback(msg){const c=document.getElementById("gmCount");if(c&&msg)c.innerHTML=msg;
  GM._gvAfter=null;GM.layout="layered";GM.expanded.clear();GM.autofit=true;gmShowGviz(false);
  GM.targets=gmSugiyama();GM.nodes.forEach(n=>{const t=GM.targets[n.i];if(t){n.x=t.x;n.y=t.y}});gmResize();gmKick()}
/* Injecting a precomputed / cached SVG needs no layout — instant and offline. */
function gmInjectSvg(host,svg){GM.gvGraphviz=null;host.innerHTML=svg;const el=host.querySelector("svg");
  if(!el)return false;host.style.position="relative";host.style.overflow="hidden";host.style.width="100%";host.style.height="100%";
  gmPanZoom(host,el);gmGvizPostRender();return true}
function gmRenderGviz(){const host=document.getElementById("gviz");if(!host)return;GM.gvRendered=false;gmShowGviz(true);
  const pre=gmPreSvg();
  const dot=pre?null:gmCurrentDot();
  const cached=pre||(dot&&GM._gvCache&&GM._gvCache[dot]);   /* precomputed overview, or a state we already laid out */
  if(cached&&gmInjectSvg(host,cached))return;
  host.innerHTML='<div class="gm-gvload">Laying out…</div>';
  /* Lay out OFF the main thread (useWorker) so a big expansion never freezes or
     crashes the tab; a watchdog drops to the crash-proof canvas view if the
     worker stalls or is unavailable (offline). Each state is cached, so it lays
     out at most once. */
  let settled=false;const done=()=>{const was=settled;settled=true;return was};
  const bail=msg=>{if(done())return;clearTimeout(timer);gmCanvasFallback(msg)};
  const timer=setTimeout(()=>bail("graph too large to lay out here — showing canvas view"),9000);
  gmEnsureGviz().then(()=>{if(settled||!gmSvgMode()||!GM.open){clearTimeout(timer);return}host.innerHTML="";
    const r=host.getBoundingClientRect();
    GM.gvGraphviz=window.d3.select(host).graphviz({useWorker:true,zoom:false}).width(r.width).height(r.height).fit(false)
      .on("end",()=>{if(done())return;clearTimeout(timer);const svg=gvSvg();
        if(dot&&svg){try{(GM._gvCache=GM._gvCache||{})[dot]=host.innerHTML}catch(_){}}
        if(svg)gmPanZoom(host,svg);GM.gvGraphviz=null;gmGvizPostRender()});
    try{GM.gvGraphviz.renderDot(dot)}catch(_){bail("showing canvas view")}})
  .catch(()=>bail("Graphviz unavailable — showing canvas view"))}
function gmGvizFit(){if(!GM.gvGraphviz&&GM.pzFit){GM.pzFit();return}
  if(GM.gvGraphviz&&typeof GM.gvGraphviz.resetZoom==="function"){try{GM.gvGraphviz.resetZoom(window.d3.transition().duration(300))}catch(_){GM.gvGraphviz.resetZoom()}}}

function openGraph(){gmBuild();
  const m=document.getElementById("graphmodal");m.classList.add("open");GM.open=true;document.body.style.overflow="hidden";
  GM.canvas=document.getElementById("gcanvas");GM.ctx=GM.canvas.getContext("2d");
  gmSelect(GM.sel!=null?GM.nodes[GM.sel]:null);
  if(!GM.inited){GM.inited=true;
    GM.targets=gmSugiyama();GM.nodes.forEach(n=>{const t=GM.targets[n.i];if(t){n.x=t.x;n.y=t.y}})}
  GM.autofit=true;gmOnReady();}
function gmOnReady(){if(!GM.open)return;const r=(GM.canvas.parentElement||GM.canvas).getBoundingClientRect();
  if(r.width<50||r.height<50){requestAnimationFrame(gmOnReady);return}
  if(gmSvgMode()){gmRenderGviz();return}   /* SVG view: leave the hidden canvas alone */
  gmResize();gmFit();gmDraw();gmKick()}
function closeGraph(){GM.open=false;document.getElementById("graphmodal").classList.remove("open");document.body.style.overflow="";hidePv();if(GM.raf){cancelAnimationFrame(GM.raf);GM.raf=null}}
function gmSelect(n){GM.sel=n?n.i:null;const side=document.getElementById("gm-side");
  if(side){side.classList.toggle("empty",!n);side.innerHTML=nodePanel(n?n.e:null);typeset(side);side.scrollTop=0}
  if(gmSvgMode())gmGvizSelect();else gmKick()}

function gmWire(){const cv=document.getElementById("gcanvas");if(!cv)return;GM.canvas=cv;
  document.getElementById("graphbtn").onclick=openGraph;
  document.getElementById("gmClose").onclick=closeGraph;
  document.getElementById("gmFit").onclick=()=>{GM.autofit=false;gmFit();gmKick()};
  const collapseAllBtn=document.getElementById("gmCollapseAll");if(collapseAllBtn)collapseAllBtn.onclick=gmCollapseAll;
  document.getElementById("gmLegend").onclick=()=>{const p=document.getElementById("gmLegendPanel");p.style.display=p.style.display==="none"?"flex":"none"};
  {const lt=document.getElementById("gmLegToggle");if(lt)lt.onclick=()=>document.getElementById("gmLegendPanel").classList.toggle("collapsed");}
  const lvl=document.getElementById("gmLevel");if(lvl){lvl.value=String(GM.lvlMax);
    /* detail level changes which declarations show inside expanded chapters —
       a real re-render (fresh DOT, fresh layout), not just hide/show */
    lvl.onchange=e=>{GM.lvlMax=+e.target.value;if(gmSvgMode()){gmRenderGviz();return}gmComputePass();gmKick()}}
  /* keep wheel/pinch on the Graphviz SVG from scrolling or zooming the whole page;
     our own pan/zoom (gmPanZoom) still reads the event and zooms the graph. */
  const gvz=document.getElementById("gviz");
  if(gvz)gvz.addEventListener("wheel",e=>{e.preventDefault();e.stopPropagation()},{passive:false});
  const csel=document.getElementById("gmChapter");
  if(csel&&DATA.chapters)DATA.chapters.forEach((ch,i)=>{const o=document.createElement("option");o.value=i;o.textContent=(ch.num+" "+plainTex(ch.title)).slice(0,42);csel.appendChild(o)});
  /* a quick way to open a specific chapter without hunting for its box; resets
     to blank right after since it's an action, not a persistent filter */
  if(csel)csel.onchange=e=>{const v=e.target.value;csel.value="";if(v!=="")gmExpandChapter(+v)};
  const q=document.getElementById("gmQ");q.oninput=()=>{GM.q=q.value.trim();gmComputePass();gmKick()};
  document.querySelectorAll(".gm-chip").forEach(c=>c.onclick=()=>{const f=c.dataset.gf;GM.gf.has(f)?GM.gf.delete(f):GM.gf.add(f);c.classList.toggle("on");gmComputePass();gmKick()});
  /* everything below only ever fires in the offline "layered" canvas fallback —
     the SVG/Graphviz path handles its own clicks via listeners on SVG elements,
     and the canvas is display:none whenever that path is active. */
  cv.addEventListener("wheel",e=>{e.preventDefault();GM.autofit=false;gmZoom(e.clientX,e.clientY,e.deltaY<0?1.12:0.893)},{passive:false});
  cv.addEventListener("mousedown",e=>{GM.autofit=false;const w=gmS2W(e.clientX,e.clientY);const n=gmHit(w.x,w.y);
    GM.down={x:e.clientX,y:e.clientY,tx:GM.tx,ty:GM.ty,node:n,moved:false};cv.classList.add("grabbing")});
  window.addEventListener("mousemove",e=>{if(!GM.open)return;
    if(GM.down){const dx=e.clientX-GM.down.x,dy=e.clientY-GM.down.y;if(dx*dx+dy*dy>16)GM.down.moved=true;
      if(GM.down.moved){GM.tx=GM.down.tx+dx;GM.ty=GM.down.ty+dy;gmKick()}return}
    const w=gmS2W(e.clientX,e.clientY);const n=gmHit(w.x,w.y);
    if(n!==GM.hover){GM.hover=n;cv.style.cursor=n?"pointer":"grab";
      if(n){const h=stmtPv(n.id);if(h)showPv(h,e.clientX,e.clientY)}else hidePv()}});
  window.addEventListener("mouseup",e=>{if(!GM.open)return;cv.classList.remove("grabbing");
    if(GM.down&&!GM.down.moved&&GM.down.node){hidePv();gmSelect(GM.down.node)}GM.down=null});
  window.addEventListener("resize",()=>{if(GM.open)gmResize()});}

/* ---- events ---- */
document.addEventListener("click",ev=>{
  if(!ev.target||!ev.target.closest)return;
  if(pvPinned&&!ev.target.closest("#pv")&&!ev.target.closest(".mtag.pop"))hidePv();
  const pop=ev.target.closest(".mtag.pop");if(pop){let h=null;
    const g=pop.getAttribute("data-graph"),le=pop.getAttribute("data-lean");
    if(g!=null)h=graphPv(g);else if(le!=null)h=leanTagPv(le);
    if(h)showPvPinned(h,ev.clientX,ev.clientY);return}
  /* sidebar expand/collapse chevrons — checked first and always return, so they
     never fall through to the navigate handlers just below (which would both
     jump to the chapter AND toggle it, since the chevron sits inside the same
     row those handlers match on) */
  const chToggle=ev.target.closest("[data-toggle-ch]");if(chToggle){const i=+chToggle.dataset.toggleCh;
    TOC_OPEN.ch.has(i)?TOC_OPEN.ch.delete(i):TOC_OPEN.ch.add(i);renderTOC();return}
  const secToggle=ev.target.closest("[data-toggle-sec]");if(secToggle){const k=secToggle.dataset.toggleSec;
    TOC_OPEN.sec.has(k)?TOC_OPEN.sec.delete(k):TOC_OPEN.sec.add(k);renderTOC();return}
  const secl=ev.target.closest("[data-sec]");if(secl){const ci=+secl.dataset.ch;clearControls();if(curCh!==ci||curView!=="doc")renderChapter(ci);
    requestAnimationFrame(()=>{const el=document.getElementById("sec-"+secl.dataset.sec);if(el){el.scrollIntoView({block:"start"});window.scrollBy(0,-84)}});return}
  const toc=ev.target.closest("#toc .tch");if(toc){clearControls();renderChapter(+toc.dataset.ch);return}
  const chl=ev.target.closest("main [data-ch]");if(chl){clearControls();renderChapter(+chl.dataset.ch);return}
  const rmore=ev.target.closest("#readyMore");if(rmore){_readyAll=!_readyAll;renderSummary();return}
  const rid=ev.target.closest(".ritem a[data-id]");if(rid){navigate(rid.dataset.id);return}
  const cite=ev.target.closest(".cite[data-cite]");if(cite){renderBiblio();requestAnimationFrame(()=>{const el=document.querySelector('.bibitem[data-key="'+cite.dataset.cite.replace(/["\\]/g,'')+'"]');if(el){el.scrollIntoView({block:"center"});el.classList.add("flash");setTimeout(()=>el.classList.remove("flash"),1700)}});return}
  const oli=ev.target.closest(".omini[data-oli]");if(oli&&oli.dataset.oli){const el=document.getElementById("stmt-"+oli.dataset.oli);
    if(el){el.scrollIntoView({block:"center"});el.classList.add("flash");setTimeout(()=>el.classList.remove("flash"),1700)}return}
  const ref=ev.target.closest(".ref[data-id]");if(ref){navigate(ref.dataset.id);return}
  const gn=ev.target.closest(".gn[data-id]");if(gn){if(GM.open)gmGoto(gn.dataset.id);else navigate(gn.dataset.id);return}
  const mm=ev.target.closest(".mm[data-goto]");if(mm&&mm.dataset.goto){navigate(mm.dataset.goto);return}
  const mmch=ev.target.closest(".mmch[data-ch]");if(mmch){renderChapter(+mmch.dataset.ch);return}
  const box=ev.target.closest(".stmt[data-nav]");if(box&&box.dataset.id){navigate(box.dataset.id)}});

document.querySelectorAll(".chip").forEach(ch=>ch.onclick=()=>{const f=ch.dataset.f;active.has(f)?active.delete(f):active.add(f);ch.classList.toggle("on");update()});
document.getElementById("q").addEventListener("input",update);
function boot(){index();stats();renderTOC();gmWire();const ov=document.getElementById("ovbtn");if(ov)ov.onclick=renderOverview;
  document.getElementById("sumbtn").onclick=renderSummary;document.getElementById("bibbtn").onclick=renderBiblio;
  /* An incoming #hash (deep link) wins over the default landing view. */
  const routed=DATA.mode==="doc"&&gotoHash();
  if(!routed){if(DATA.mode==="doc"&&DATA.chapters.length)renderOverview();else if(DATA.mode==="doc")renderChapter(0);}
  window.addEventListener("hashchange",()=>{if(HASHNAV)return;gotoHash()});
  window.addEventListener("load",()=>{typesetLazy(document.getElementById("main"));
    ["toc","outline"].forEach(id=>typeset(document.getElementById(id)))});}
if(DATA)boot();else fetch("/api/graph").then(r=>r.json()).then(d=>{DATA=d;boot()});
</script></body></html>
"""
