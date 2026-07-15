"""`hgraph site` — a lightweight multi-project landing page.

Reads a small YAML manifest describing several hgraph projects, computes each
project's formalization progress (reusing :class:`~hgraph.analysis.Analysis`),
and emits a single ``index.html``: one card per project (a segmented progress
bar + counts) linking to that project's dashboard, above a bespoke *overview*
fragment — e.g. a hand-authored proof-structure diagram whose boxes deep-link
into the per-project dashboards.

The page shares the dashboards' design tokens (same palette, type, header) so
the landing and the blueprints read as one product, and it loads KaTeX so the
overview can carry real LaTeX. It stays small: the heavy per-project
``dashboard.html`` files load only when a card/box is clicked.

Manifest schema (paths are resolved relative to the manifest file)::

    title: OpenGA — Poincaré Formalization
    subtitle: A machine-verified path to the Poincaré conjecture
    overview: overview.html          # optional fragment injected below the hero
    projects:
      - name: Riemannian Geometry (do Carmo)
        root: DoCarmo                # dir containing hgraph/
        href: DoCarmo/dashboard.html # link target (default: <root>/dashboard.html)
        tag: Book I                  # optional short label
        blurb: Foundations — metrics, curvature, comparison geometry.
"""

from __future__ import annotations

import html
from pathlib import Path

import yaml

from .analysis import Analysis
from .dashboard import _KATEX_CDN, _vendor_katex
from .graph import Graph

_DONE = {"lean_ok", "mathlib_ok"}


def project_progress(root: str | Path) -> dict:
    """Open the hgraph project at ``root`` and summarise its progress over the
    blueprint (``tex``) statements — the same quantity the dashboard bars show."""
    g = Graph.open(str(root))
    tex = list(g.nodes(type="tex"))
    done = sum(1 for n in tex if n.meta.get("lean_status") in _DONE)
    partial = sum(1 for n in tex if n.meta.get("lean_status") == "sorry")
    total = len(tex)
    return {
        "statements": total,
        "done": done,
        "partial": partial,
        "todo": total - done - partial,
        "pct": round(100 * done / total) if total else 0,
        "closed": Analysis(g).state_counts().get("closed", 0),
    }


def _esc(s) -> str:
    return html.escape(str(s or ""))


def _card(p: dict, prog: dict) -> str:
    total = prog["statements"] or 1
    seg = lambda n, cls: (f'<i class="{cls}" style="width:{100 * n / total:.4f}%"></i>'
                          if n else "")
    bar = seg(prog["done"], "s-done") + seg(prog["partial"], "s-part") + seg(prog["todo"], "s-todo")
    tag = f'<span class="ctag">{_esc(p["tag"])}</span>' if p.get("tag") else ""
    blurb = f'<p class="blurb">{_esc(p["blurb"])}</p>' if p.get("blurb") else ""
    return f'''<a class="card" href="{_esc(p["href"])}">
      <div class="chead">{tag}<span class="pct">{prog["pct"]}<small>%</small></span></div>
      <h3>{_esc(p["name"])}</h3>
      {blurb}
      <div class="pbar" role="img" aria-label="{prog["pct"]}% formalized">{bar}</div>
      <div class="counts">
        <span><b>{prog["statements"]}</b> statements</span>
        <span class="c-done">{prog["done"]} formalized</span>
        {f'<span class="c-part">{prog["partial"]} in&nbsp;progress</span>' if prog["partial"] else ""}
        <span class="c-todo">{prog["todo"]} to&nbsp;do</span>
      </div>
      <span class="open">Open blueprint&nbsp;&rarr;</span>
    </a>'''


_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
__KATEX_HEAD__
<style>
/* Shared design tokens with the per-project dashboards. */
:root{--bg:#f4f5f7;--panel:#fff;--fg:#1c2024;--muted:#6b7280;--line:#e2e5ea;--soft:#f0f2f5;
 --accent:#4f46e5;--lean:#137333;--sorry:#c2410c;--empty:#9aa2ad;--mathlib:#0b5fd0;
 --shadow:0 1px 2px rgba(20,25,35,.05),0 4px 14px rgba(20,25,35,.05)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font:15px/1.62 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,sans-serif;
 -webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
header{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.9);
 backdrop-filter:saturate(1.4) blur(8px);border-bottom:1px solid var(--line);padding:11px 24px}
.htop{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;max-width:1120px;margin:0 auto}
.brand{font-size:17px;font-weight:800;letter-spacing:-.01em}
.htop .sub{color:var(--muted);font-size:13px}
.htop .agg{margin-left:auto;font-size:12.5px;color:var(--muted);white-space:nowrap}
.htop .agg b{color:var(--fg);font-size:14px}
.htop .agg .pbar{width:120px;margin-left:8px;vertical-align:middle}
.wrap{max-width:1120px;margin:0 auto;padding:44px 24px 96px}
.hero{text-align:center;max-width:760px;margin:0 auto}
.hero h1{font-size:clamp(26px,3.6vw,38px);line-height:1.12;letter-spacing:-.02em;margin:0 0 14px;font-weight:800}
.hero p.sub{color:var(--muted);font-size:clamp(14.5px,1.7vw,17px);max-width:66ch;margin:0 auto;
 text-align:justify;text-align-last:center}
h2.sec{font-size:12px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);
 margin:52px 0 18px;font-weight:700;text-align:center}
/* progress bars (shared look: blue→green formalized, orange in-progress, grey to-do) */
.pbar{display:flex;height:7px;border-radius:5px;overflow:hidden;background:var(--soft)}
.pbar i{display:block;height:100%}
.s-done{background:linear-gradient(90deg,var(--mathlib),var(--lean))}
.s-part{background:var(--sorry)}.s-todo{background:var(--empty);opacity:.5}
/* project cards */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:18px}
.card{display:flex;flex-direction:column;gap:9px;color:inherit;background:var(--panel);
 border:1px solid var(--line);border-radius:14px;padding:20px;box-shadow:var(--shadow);
 transition:transform .15s,border-color .15s,box-shadow .15s}
.card:hover{transform:translateY(-3px);border-color:var(--accent);
 box-shadow:0 2px 4px rgba(20,25,35,.06),0 14px 34px rgba(30,30,60,.12)}
.chead{display:flex;align-items:center;justify-content:space-between;min-height:22px}
.ctag{font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--accent);
 background:color-mix(in srgb,var(--accent) 10%,#fff);padding:3px 9px;border-radius:999px}
.pct{font-variant-numeric:tabular-nums;font-weight:800;font-size:20px}.pct small{font-size:12px;color:var(--muted);font-weight:700}
.card h3{margin:0;font-size:18px;line-height:1.25;letter-spacing:-.01em}
.blurb{margin:0;color:var(--muted);font-size:13px;line-height:1.5}
.counts{display:flex;flex-wrap:wrap;gap:3px 13px;font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
.counts b{color:var(--fg)}.c-done{color:var(--lean)}.c-part{color:var(--sorry)}
.open{margin-top:4px;font-size:12.5px;font-weight:700;color:var(--accent);opacity:0;transform:translateX(-4px);transition:.15s}
.card:hover .open{opacity:1;transform:none}
.legend{display:flex;flex-wrap:wrap;gap:16px;margin-top:14px;font-size:12.5px;color:var(--muted)}
.legend i{display:inline-block;width:22px;height:7px;border-radius:4px;margin-right:6px;vertical-align:middle}
footer{margin-top:64px;color:var(--muted);font-size:12.5px;border-top:1px solid var(--line);padding-top:20px}
.katex{font-size:1.02em}
</style>
</head>
<body>
<header><div class="htop"><span class="brand">__BRAND__</span>__AGG__</div></header>
<div class="wrap">
  <div class="hero">
    <h1>__TITLE__</h1>
    <p class="sub">__SUBTITLE__</p>
  </div>
__MAIN__
__FOOTER__
</div>
<script>
addEventListener("DOMContentLoaded",function(){
  if(window.renderMathInElement) renderMathInElement(document.body,{delimiters:[
    {left:"$$",right:"$$",display:true},{left:"$",right:"$",display:false}],throwOnError:false});
});
</script>
</body>
</html>
"""


def build_site(manifest: dict, *, base: Path, overview_html: str | None = None,
               self_contained: bool = True) -> str:
    """Render the landing ``index.html`` from a parsed ``manifest``. ``base`` is
    the directory the manifest's relative paths resolve against."""
    title = manifest.get("title", "Blueprint projects")

    ov = overview_html
    if ov is None and manifest.get("overview"):
        ov = (base / manifest["overview"]).read_text(encoding="utf-8")
    overview_block = f'  <section class="overview">\n{ov}\n  </section>' if ov else ""

    cards, tot_done, tot_stmts = [], 0, 0
    for p in manifest.get("projects", []):
        p = dict(p)
        p.setdefault("href", f'{p["root"]}/dashboard.html')
        try:
            prog = project_progress(base / p["root"])
            tot_done += prog["done"]; tot_stmts += prog["statements"]
        except Exception as e:
            prog = {"statements": 0, "done": 0, "partial": 0, "todo": 0, "pct": 0, "closed": 0}
            p.setdefault("blurb", f"(progress unavailable: {e})")
        cards.append(_card(p, prog))
    cards_html = "\n".join(cards)

    projects_block = f'''  <h2 class="sec">Projects</h2>
  <div class="grid">
{cards_html}
  </div>
  <div class="legend">
    <span><i class="s-done"></i>formalized in Lean</span>
    <span><i class="s-part"></i>stated, proof in progress</span>
    <span><i class="s-todo"></i>to do</span>
  </div>'''

    # The project cards are the primary content and lead; the (optional) overview
    # diagram follows. Set `overview_position: above` in the manifest to place the
    # overview between the hero and the cards instead.
    if manifest.get("overview_position", "below") == "above":
        blocks = [overview_block, projects_block]
    else:
        blocks = [projects_block, overview_block]
    main = "\n".join(b for b in blocks if b)

    # header KaTeX (vendored for offline, falling back to CDN)
    katex = _KATEX_CDN
    if self_contained:
        try:
            katex = _vendor_katex()
        except Exception:
            pass

    # aggregate progress chip in the header, mirroring a dashboard's stats
    agg = ""
    if tot_stmts:
        pct = round(100 * tot_done / tot_stmts)
        agg = (f'<span class="agg"><b>{pct}%</b> formalized · {tot_done}/{tot_stmts}'
               f'<span class="pbar" style="display:inline-flex">'
               f'<i class="s-done" style="width:{pct}%"></i></span></span>')

    footer = manifest.get("footer",
                          'Built with <a href="https://github.com/AxelDlv00/hgraph">hgraph</a> — '
                          'a plain-files semantic graph for autoformalization.')

    return (_PAGE
            .replace("__KATEX_HEAD__", katex)
            .replace("__BRAND__", _esc(manifest.get("brand", manifest.get("title", "Blueprint"))))
            .replace("__AGG__", agg)
            .replace("__TITLE__", _esc(title))
            .replace("__SUBTITLE__", _esc(manifest.get("subtitle", "")))
            .replace("__MAIN__", main)
            .replace("__FOOTER__", f"<footer>{footer}</footer>"))


def build_from_manifest(manifest_path: str | Path, *,
                        overview_path: str | Path | None = None,
                        self_contained: bool = True) -> str:
    mp = Path(manifest_path)
    manifest = yaml.safe_load(mp.read_text(encoding="utf-8")) or {}
    overview_html = (Path(overview_path).read_text(encoding="utf-8")
                     if overview_path else None)
    return build_site(manifest, base=mp.parent, overview_html=overview_html,
                      self_contained=self_contained)
