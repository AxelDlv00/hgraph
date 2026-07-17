"""`hgraph site` — the whole site (a React/Vite frontend, single-page).

There is no separate per-project "dashboard" artifact: one project or many,
it's all one app. Reads a small YAML manifest describing the project(s),
computes each one's formalization progress (reusing
:class:`~hgraph.analysis.Analysis`), and either:

* writes a static ``index.html`` + a sibling ``assets/`` dir — the pre-built
  frontend at :data:`WEBUI_DIR` (shipped with the package, no Node needed) —
  plus one ``<root>/data.json`` per project, with the landing data injected
  as ``window.__HGRAPH_DATA__``; or
* (see :mod:`hgraph.server`) is served live, with the landing data instead
  fetched from ``GET /api/site`` and each project's from ``GET
  /<root>/data.json``.

The frontend hash-routes from the landing page to a project (``#/<root>``)
client-side — no extra HTML file, no server-side routing needed either way.

Everything is written under ``--out``'s directory (``_site/`` by default), so
generated files never mix into the sources they were built from::

    _site/
      index.html                     the landing page (data injected inline)
      assets/                        the pre-built frontend bundle
      examples/gauss/data.json       one per project in the manifest
      examples/triangular/data.json

That tree is the whole deployable site — it is what ``.github/workflows/
pages.yml`` publishes, with nothing to assemble by hand.

Manifest schema (paths are resolved relative to the manifest file)::

    title: OpenGA — Poincaré Formalization
    subtitle: A machine-verified path to the Poincaré conjecture
    tab_title: OpenGA                # optional — the browser-tab <title>; falls
                                      # back to brand, then title, then "hgraph"
    favicon: img/logo.svg            # optional — the tab icon: a path relative
                                      # to this manifest (inlined), a URL/data
                                      # URI, or an emoji (🌀) drawn onto an SVG
    overview: overview.md            # optional fragment injected below the hero
                                      # (.md is converted; .html is used verbatim)
    repo: owner/name                 # optional — the default `repo:` for every
                                      # project below that does not set its own.
                                      # Projects of one monorepo share it rather
                                      # than repeating it per entry. A full
                                      # GitHub URL is accepted and reduced.
    categories:                      # optional — a line under a category heading.
      Riemannian Geometry: The core machinery: metrics, curvature, geodesics.
      Algebraic Topology:            # the longer spelling, same thing
        subtitle: Fundamental group, covering spaces, homology.
                                      # keyed by the projects' `category:`; a
                                      # category with no entry has no subtitle
    projects:
      - name: Riemannian Geometry (do Carmo)
        root: DoCarmo                # dir containing hgraph/
        category: Differential Geometry  # optional — projects sharing a category
                                          # render grouped under one heading; a
                                          # manifest that never sets it renders one
                                          # flat "Projects" section
        author: do Carmo             # optional — shown in serif on the card
        book_title: Riemannian Geometry  # optional — falls back to `name`
        tag: Book I                  # optional short label (pill; "\\n" -> two lines)
        icon: hierarchy              # optional — see frontend/src/components/Icon.tsx
        image: img/gauss.jpg         # optional picture for the card panel, instead of
                                      # `icon` — a path relative to this manifest (it is
                                      # inlined into the page, so keep it small) or a URL
        image_alt: Portrait of Gauss # optional — falls back to the card title
        image_offset: 20             # optional — how far down the picture the 180px
                                      # card panel crops: 0 (default) keeps its top,
                                      # 100 its bottom. Bare numbers are percentages;
                                      # any CSS value also works (`top`, `-30px`).
                                      # Only applies when image_fit is `cover`.
        image_fit: contain           # optional — `cover` (default) fills the panel and
                                      # crops; `contain` fits the whole picture in, with
                                      # the gradient around it (right for a book cover:
                                      # portrait picture, landscape panel)
        links: [{label: Formalization, href: ...}, {label: Docs, href: ...}]
        blurb: Foundations — metrics, curvature, comparison geometry.
        repo: owner/name             # optional — enables the GitHub-issue review link.
                                      # Defaults to the page-level `repo:` above;
                                      # set it only where a project lives in its
                                      # own repo.

With no ``--manifest``, ``hgraph site`` first looks for a workspace-level
``config.yaml`` in this shape next to the project directories; failing that, it
synthesizes a single-project manifest from ``./hgraph/config.yaml``'s ``site:``
block (see :func:`hgraph.sync.load_config`) — a solo project needs no manifest
file of its own, and still gets the same landing page + project view.

That ``site:`` block takes the page's keys, plus every card key above for its
one card (paths are relative to the project root)::

    site:
      title: do Carmo — Riemannian Geometry
      subtitle: The shared foundation — metrics, connections, curvature.
      tab_title: do Carmo        # optional — browser-tab <title> (see above)
      favicon: img/logo.svg      # optional — tab icon: path / URL / emoji
      overview: overview.md      # without one the page is a hero and a lone card
      repo: owner/name
      card_title: Blueprint      # the card's own name; defaults to `title`, but
                                 # then the title shows twice, which reads as a
                                 # stutter — give the card a different name
      tag: 495 statements        # and any of: author, book_title, icon, blurb,
      icon: book                 # links, image, image_alt, image_offset, image_fit
"""

from __future__ import annotations

import base64
import html
import json
import mimetypes
import re
import shutil
import urllib.parse
from pathlib import Path

import yaml

from .analysis import Analysis
from .graph import Graph, HGraphError

_DONE = {"lean_ok", "mathlib_ok"}

# the pre-built frontend (see frontend/README-DEV.md) — shipped as package
# data, so this exists whether hgraph was installed with `pip install .` or
# `pip install -e .`; no Node required at the user's end.
WEBUI_DIR = Path(__file__).parent / "webui"


def _md_to_html(text: str) -> str:
    """Tiny, dependency-free Markdown → HTML for the overview fragment:
    ``#``/``##``/``###`` headings, paragraphs, ``**bold**``, ``*italic*``,
    `` `code` ``, ``[text](url)`` links, ``-``/``*`` bullet lists. Not a
    general Markdown parser — just enough for a short landing-page blurb.

    A list item may wrap over several lines (Markdown's lazy continuation): the
    following lines fold into the item until a blank line, another bullet, or a
    heading ends it. Without that, a hard-wrapped bullet — the normal way to
    write one — used to emit a ``<p>`` *inside* the ``<ul>``, which is invalid
    HTML and rendered with the wrong spacing."""
    def inline(s: str) -> str:
        s = _esc(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<i>\1</i>", s)
        s = re.sub(r"`([^`]+?)`", r"<code>\1</code>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        return s

    out: list[str] = []
    para: list[str] = []
    item: list[str] = []          # the list item currently being collected
    list_open = False

    def flush_para():
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()

    def flush_item():
        if item:
            out.append("<li>" + inline(" ".join(item)) + "</li>")
            item.clear()

    def close_list():
        nonlocal list_open
        flush_item()
        if list_open:
            out.append("</ul>")
            list_open = False

    for raw in text.splitlines():
        line = raw.rstrip()
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            flush_para(); close_list()
            level = len(m.group(1)) + 2   # h3..h5 — nests under the page's own h1/h2
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            continue
        m = re.match(r"^[-*]\s+(.*)", line)
        if m:
            flush_para(); flush_item()
            if not list_open:
                out.append("<ul>"); list_open = True
            item.append(m.group(1))
            continue
        if not line.strip():
            flush_para(); close_list()
            continue
        if list_open:                 # a wrapped continuation of the open item
            item.append(line.strip())
            continue
        para.append(line.strip())
    flush_para(); close_list()
    return "\n".join(out)


def looks_like_manifest(path: str | Path) -> bool:
    """Is ``path`` an hgraph site manifest — a ``projects:`` *list* whose entries
    carry a ``root:``?

    ``hgraph site``/``serve`` auto-discover ``./config.yaml``, but that filename
    is popular: an Archon/Horizon workspace keeps its own there, with a
    ``projects:`` *mapping* of a completely different shape. Without this check
    the build gets several frames deep and dies on a ``TypeError: string indices
    must be integers``, which tells the user nothing. Anything unreadable or
    unrecognised is simply "not a manifest", so the caller can fall through to
    the solo path and explain itself."""
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    projects = data.get("projects")
    if not isinstance(projects, list) or not projects:
        return False
    return all(isinstance(p, dict) and p.get("root") is not None for p in projects)


def _read_overview(path: str | Path) -> str:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    return _md_to_html(text) if path.suffix == ".md" else text


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


# a card picture is inlined as a data URI rather than copied next to the page:
# the same site data feeds the static export and `hgraph serve`, so inlining
# means one code path and no extra route/asset to keep in sync.
_INLINE_IMAGE_WARN = 512 * 1024

# The card panel is 180px tall and its column is ~340-450px wide, so this box
# is roughly 2x the biggest it is ever painted — enough to stay sharp on a
# retina screen, and small enough that a photo costs tens of KB, not hundreds.
_CARD_IMAGE_BOX = (800, 800)
_CARD_JPEG_QUALITY = 82
# An image that already fits the box and is this small is left byte-for-byte
# alone: re-encoding it could only shave a little off, at the cost of a
# generation of JPEG loss on a picture the author already tuned.
_CARD_IMAGE_KEEP = 128 * 1024


def _card_fit(value) -> str | None:
    """Normalise a project's ``image_fit:``. ``contain`` fits the whole picture
    into the card panel (right for a book cover: it is portrait, the panel is
    landscape, so ``cover`` would show only a band of it); ``cover`` — the
    default — fills the panel and crops the overflow."""
    if value is None or value == "":
        return None
    fit = str(value).strip().lower()
    if fit not in ("cover", "contain"):
        raise HGraphError(f"image_fit must be 'cover' or 'contain', not {value!r}")
    return fit


def _card_offset(value) -> str | None:
    """Normalise a project's ``image_offset:`` to a CSS vertical position — a
    bare number means percent (``20`` -> ``20%``), anything else is passed
    through as written (``top``, ``-30px``, ...)."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return f"{value:g}%"
    src = str(value).strip()
    return f"{src}%" if re.fullmatch(r"-?\d+(\.\d+)?", src) else src


def _shrink_image(raw: bytes) -> tuple[bytes, str] | None:
    """Downscale a card picture to :data:`_CARD_IMAGE_BOX` and re-encode it,
    returning ``(bytes, content-type)`` — or ``None`` if Pillow isn't installed,
    the bytes aren't a picture Pillow groks, or the result is no smaller (an
    already-tuned image is left exactly as the author made it). The source file
    is only ever read, never rewritten."""
    try:
        from PIL import Image                      # optional — see pyproject's `images` extra
    except ImportError:
        return None
    import io
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception:
        return None

    if im.format == "GIF" and getattr(im, "is_animated", False):
        return None                                # would flatten to a single frame

    was = im.size
    im.thumbnail(_CARD_IMAGE_BOX, Image.LANCZOS)   # only ever shrinks, keeps aspect
    if im.size == was and len(raw) <= _CARD_IMAGE_KEEP:
        return None
    # Photos re-encode far smaller as JPEG; keep PNG only where alpha matters,
    # since the card panel would show the page through a transparent hole.
    alpha = im.mode in ("RGBA", "LA") or "transparency" in im.info
    buf = io.BytesIO()
    if alpha:
        im.convert("RGBA").save(buf, "PNG", optimize=True)
        ctype = "image/png"
    else:
        im.convert("RGB").save(buf, "JPEG", quality=_CARD_JPEG_QUALITY, optimize=True,
                               progressive=True)
        ctype = "image/jpeg"
    out = buf.getvalue()
    return (out, ctype) if len(out) < len(raw) else None


def _card_image(value, *, base: Path) -> str | None:
    """Resolve a project's ``image:`` to something a browser can render: URLs
    (and data URIs) pass through, a path relative to ``base`` is shrunk to card
    size and inlined."""
    if not value:
        return None
    src = str(value)
    if re.match(r"^(https?:|data:|//)", src):
        return src
    path = (base / src).resolve()
    if not path.is_file():
        print(f"warning: card image not found, ignoring: {path}")
        return None
    raw = path.read_bytes()
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    shrunk = _shrink_image(raw)
    if shrunk:
        raw, ctype = shrunk
    elif len(raw) > _INLINE_IMAGE_WARN:
        print(f"warning: card image {path.name} is {len(raw) // 1024} KB and is inlined "
              f"into the page as-is — install Pillow (`pip install 'hgraph[images]'`) to "
              f"have it downscaled automatically, or shrink it by hand")
    return f"data:{ctype};base64,{base64.b64encode(raw).decode('ascii')}"


# image suffixes that mark a bare `favicon:` value as a file path rather than
# an emoji, even when it names no directory (a bare "logo.svg" next to the
# manifest)
_FAVICON_EXTS = (".svg", ".png", ".ico", ".jpg", ".jpeg", ".gif", ".webp")


def _favicon_source(value, *, base: Path) -> tuple[str, str | None] | None:
    """Resolve a manifest ``favicon:`` to ``(href, type)`` for a
    ``<link rel="icon">`` — or ``None`` to leave the page without one.

    Three spellings, each the natural way to reach for it:

    * a URL or ``data:`` URI — used as written;
    * a path relative to the manifest (``img/logo.svg``) — inlined as a data
      URI, so the static export and ``hgraph serve`` need no extra asset or
      route (same reasoning as a card ``image:``);
    * anything else short — an emoji (``🌀``) or a letter — drawn onto a tiny
      SVG, the zero-effort way to give a page its own tab icon.
    """
    if value is None:
        return None
    src = str(value).strip()
    if not src:
        return None
    if re.match(r"^(https?:|data:|//)", src):
        # a data: URI carries its own media type; a plain URL we type by suffix
        ctype = None if src.startswith("data:") else mimetypes.guess_type(src)[0]
        return src, ctype
    candidate = base / src
    if "/" in src or "\\" in src or src.lower().endswith(_FAVICON_EXTS) or candidate.is_file():
        path = candidate.resolve()
        if not path.is_file():
            print(f"warning: favicon not found, ignoring: {path}")
            return None
        raw = path.read_bytes()
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if len(raw) > _INLINE_IMAGE_WARN:
            print(f"warning: favicon {path.name} is {len(raw) // 1024} KB and is inlined "
                  f"into the page as-is — a tab icon this large is almost certainly a "
                  f"mistake; point favicon: at a small .svg/.png or an emoji")
        return f"data:{ctype};base64,{base64.b64encode(raw).decode('ascii')}", ctype
    # an emoji / short label -> a self-contained SVG tab icon
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
           '<text x="50" y="52" font-size="72" text-anchor="middle" '
           f'dominant-baseline="central">{html.escape(src)}</text></svg>')
    return "data:image/svg+xml," + urllib.parse.quote(svg), "image/svg+xml"


def _favicon_link(value, *, base: Path) -> str:
    """The ``<link rel="icon">`` tag for a manifest ``favicon:``, or ``""``."""
    src = _favicon_source(value, base=base)
    if not src:
        return ""
    href, ctype = src
    type_attr = f' type="{_esc(ctype)}"' if ctype else ""
    return f'<link rel="icon"{type_attr} href="{_esc(href)}" />'


def render_index_html(manifest: dict, *, base: Path, data_script: str = "") -> str:
    """The shipped webui ``index.html`` with this manifest's tab title and
    favicon applied — and, for the static export, the site-data ``<script>``
    injected. Shared by :func:`write_static_site` and the live servers so the
    tab reads the same either way.

    * ``tab_title:`` sets the ``<title>`` (the browser-tab text); it falls back
      to ``brand:``, then ``title:``, then ``hgraph``.
    * ``favicon:`` sets the tab icon (see :func:`_favicon_source`).
    """
    html_text = (WEBUI_DIR / "index.html").read_text(encoding="utf-8")
    tab_title = (manifest.get("tab_title") or manifest.get("brand")
                 or manifest.get("title") or "hgraph")
    html_text = html_text.replace("<title>hgraph</title>",
                                  f"<title>{_esc(tab_title)}</title>", 1)
    icon = _favicon_link(manifest.get("favicon"), base=base)
    if icon:
        html_text = html_text.replace("<title>", icon + "\n    <title>", 1)
    if data_script:
        html_text = html_text.replace("<!-- __HGRAPH_DATA__:",
                                      data_script + "<!-- __HGRAPH_DATA__:", 1)
    return html_text


def _category_subtitles(value) -> dict[str, str]:
    """Normalise the manifest's optional ``categories:`` into {category:
    subtitle}. Two spellings, because both are natural to write::

        categories:
          Riemannian Geometry: The core machinery.        # shorthand
          Algebraic Topology:
            subtitle: Fundamental group and homology.     # room to grow

    Keyed by the same string the projects' ``category:`` uses — a category with
    no entry here simply has no subtitle, which is the point of it being
    optional."""
    if not value:
        return {}
    if not isinstance(value, dict):
        raise HGraphError("categories: must be a mapping of category name -> subtitle")
    out: dict[str, str] = {}
    for name, v in value.items():
        if isinstance(v, dict):
            v = v.get("subtitle")
        if v is None or v == "":
            continue
        if not isinstance(v, str):
            raise HGraphError(f"categories: {name!r} subtitle must be text, not {type(v).__name__}")
        out[str(name)] = " ".join(v.split())   # fold YAML's wrapped `>` lines
    return out


def build_site_data(manifest: dict, *, base: Path, overview_html: str | None = None) -> dict:
    """Compute the JSON-able site data — matches ``frontend/src/types.ts``'s
    ``SiteData``. Used for both the static export (embedded as
    ``window.__HGRAPH_DATA__``) and the live ``GET /api/site`` endpoint."""
    ov = overview_html
    if ov is None and manifest.get("overview"):
        ov = _read_overview(base / manifest["overview"])

    # Group by `category` (order of first appearance); projects without one
    # fall into a single untitled group, rendered as a flat "Projects" section.
    groups: dict[str | None, list[dict]] = {}
    for p in manifest.get("projects", []):
        p = dict(p)
        try:
            prog = project_progress(base / p["root"])
        except Exception as e:
            prog = {"statements": 0, "done": 0, "partial": 0, "todo": 0, "pct": 0}
            p.setdefault("blurb", f"(progress unavailable: {e})")
        card = {
            "name": p["name"],
            "root": str(p["root"]).strip("/"),   # the frontend hash-routes to #/<root>
            "category": p.get("category"),
            "author": p.get("author"),
            "bookTitle": p.get("book_title"),
            "tag": p.get("tag"),
            "links": p.get("links"),
            "icon": p.get("icon"),
            "image": _card_image(p.get("image"), base=base),
            "imageAlt": p.get("image_alt"),
            "imageOffset": _card_offset(p.get("image_offset")),
            "imageFit": _card_fit(p.get("image_fit")),
            "blurb": p.get("blurb"),
            "stats": {k: prog[k] for k in ("statements", "done", "partial", "todo", "pct")},
        }
        groups.setdefault(p.get("category"), []).append(card)

    subs = _category_subtitles(manifest.get("categories"))
    unused = set(subs) - {c for c in groups if c is not None}
    for cat in sorted(unused):
        print(f"warning: categories: {cat!r} matches no project's category: — ignored")

    return {
        "title": manifest.get("title", "Blueprint projects"),
        "subtitle": manifest.get("subtitle"),
        "brand": manifest.get("brand"),
        "overviewHtml": ov,
        "footer": manifest.get("footer"),
        "sections": [{"category": cat, "subtitle": subs.get(cat), "projects": cards}
                     for cat, cards in groups.items()],
    }


def _copy_webui(out_dir: Path) -> None:
    """Copy the pre-built frontend into ``out_dir``, *merging* into directories
    that are already there rather than replacing them.

    The output dir is very often the project itself (``hgraph site --out
    index.html`` from a project root, as the examples' build.sh does), so
    ``out_dir/assets`` can be a directory the user keeps their own files in —
    a card picture, say. We overwrite what we ship and leave everything else
    alone, rather than ``rmtree``-ing the whole dir (which once ate a card image
    a user had put there).

    But our *own* files are content-hashed (``assets/index-<hash>.js`` etc.), so
    a plain merge leaves last build's bundle behind next to this one — harmless
    to the page (index.html names only the current hash) but, in a committed
    ``docs/`` that is rebuilt over and over, an ever-growing pile of orphans.
    So we prune stale copies of *our* hashed bundles first — matched by the
    exact naming Vite gives them — while still never touching a name we don't
    recognise as ours."""
    # our shipped files, and the hashed-bundle names to prune when orphaned
    shipped = {src.relative_to(WEBUI_DIR)
               for src in WEBUI_DIR.rglob("*") if src.is_file()}
    ours = re.compile(r"^(index|viz)-[A-Za-z0-9_-]+\.(js|css)$")
    assets = out_dir / "assets"
    if assets.is_dir():
        for f in assets.iterdir():
            if f.is_file() and ours.match(f.name) and Path("assets", f.name) not in shipped:
                f.unlink()

    for src in WEBUI_DIR.rglob("*"):
        rel = src.relative_to(WEBUI_DIR)
        if rel.parts[0] == "index.html":                 # injected separately, below
            continue
        dst = out_dir / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def write_static_site(manifest: dict, *, base: Path, out_path: str | Path,
                      overview_html: str | None = None) -> None:
    """Write the whole site as static files: ``out_path`` (an ``index.html``)
    plus a sibling ``assets/`` dir copied from the
    pre-built frontend, the landing data injected as
    ``window.__HGRAPH_DATA__``, and one ``<root>/data.json`` per project (see
    :func:`hgraph.dashboard.project_data`) — everything the React
    `ProjectView` route needs, fetched relative to wherever the page is
    served from, no server required."""
    from .dashboard import project_data
    from .graph import Graph

    out_path = Path(out_path)
    out_dir = out_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    _copy_webui(out_dir)

    for p in manifest.get("projects", []):
        proot = base / p["root"]
        data = project_data(Graph.open(str(proot)), title=p.get("name", p["root"]),
                            root=str(proot), repo=p.get("repo") or manifest.get("repo"))
        data_dir = out_dir / str(p["root"]).strip("/")
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "data.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")

    data = build_site_data(manifest, base=base, overview_html=overview_html)
    inject = f"<script>window.__HGRAPH_DATA__={json.dumps(data, ensure_ascii=False)}</script>\n    "
    out_path.write_text(render_index_html(manifest, base=base, data_script=inject),
                        encoding="utf-8")


def write_from_manifest(manifest_path: str | Path, *, out_path: str | Path,
                        overview_path: str | Path | None = None) -> None:
    mp = Path(manifest_path)
    manifest = yaml.safe_load(mp.read_text(encoding="utf-8")) or {}
    overview_html = _read_overview(overview_path) if overview_path else None
    write_static_site(manifest, base=mp.parent, out_path=out_path, overview_html=overview_html)


# Card keys a solo project's `site:` block may set; they mean exactly what they
# mean in a manifest entry (see this module's docstring). `name`/`root` are
# synthesized, and `title`/`subtitle`/`overview`/`repo` belong to the page
# rather than the card, so they are handled separately in write_solo.
_SOLO_CARD_KEYS = ("card_title", "author", "book_title", "tag", "icon", "blurb", "links",
                   "image", "image_alt", "image_offset", "image_fit")


def solo_manifest(site_cfg: dict, *, title: str = "Blueprint", repo=None) -> dict:
    """The one-project manifest a solo project's ``site:`` block stands for.

    Shared by the static export (:func:`write_solo`) and the live server
    (:func:`hgraph.server.serve`) so the two cannot describe the same project
    differently. The card gets every card key the block sets, so a solo page is
    as rich as a manifest-built one. Its name defaults to `card_title`, falling
    back to the page title — set `card_title` when repeating the page title on
    the card below it reads as a stutter."""
    site_title = site_cfg.get("title", title)
    card = {k: site_cfg[k] for k in _SOLO_CARD_KEYS if site_cfg.get(k) is not None}
    card.pop("card_title", None)
    manifest = {
        "title": site_title,
        "subtitle": site_cfg.get("subtitle", ""),
        "overview": site_cfg.get("overview"),
        "projects": [{
            "name": site_cfg.get("card_title") or site_title,
            "root": ".",
            "repo": repo or site_cfg.get("repo"),
            **card,
        }],
    }
    # page-level keys (not card keys) — the header brand and the tab's
    # title/icon carry over from a solo `site:` block just as from a manifest
    for k in ("brand", "tab_title", "favicon", "footer"):
        if site_cfg.get(k) is not None:
            manifest[k] = site_cfg[k]
    return manifest


def write_solo(site_cfg: dict, *, root: str | Path, out_path: str | Path,
              overview_path: str | Path | None = None) -> None:
    """A single-project landing page synthesized from a project's own
    ``hgraph/config.yaml`` -> ``site:`` block — no manifest file needed."""
    manifest = solo_manifest(site_cfg)
    overview_html = _read_overview(overview_path) if overview_path else None
    write_static_site(manifest, base=Path(root), out_path=out_path, overview_html=overview_html)
