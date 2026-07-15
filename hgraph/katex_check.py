"""Validate blueprint math against real KaTeX before serving/exporting.

Broken math (an undefined macro, a construct KaTeX's grammar rejects) otherwise
surfaces only as a blank render discovered one node at a time in the browser. This
module runs the actual ``katex`` npm package (Node) over every math span in the
document and turns failures into ``warning: ...`` lines, the same convention as the
existing bib / lean / ``\\uses`` warnings from :mod:`hgraph.sync`.

It is a **pure optimisation / diagnostic**, exactly like ``layout.py``'s ``dot``
precompute: if Node or the ``katex`` package isn't available, :func:`check_katex`
returns ``[]`` silently and nothing else is affected.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

_JS = Path(__file__).with_name("_katex_validate.js")
_NODE_MODULES = str(Path(__file__).resolve().parent.parent / "node_modules")


def katex_available() -> bool:
    """True iff ``node`` is on PATH and the bundled ``katex`` package resolves."""
    if not shutil.which("node"):
        return False
    try:
        r = subprocess.run(
            ["node", "-e", "require.resolve('katex')"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "NODE_PATH": _NODE_MODULES},
        )
        return r.returncode == 0
    except Exception:
        return False


def _iter_text_blocks(chapters: list[dict]):
    """Yield (ref, text) for every prose / statement / proof block in a parsed
    document (:func:`hgraph.sync.parse_document`'s ``chapters`` return value)."""
    for ch in chapters:
        title = ch.get("title") or "?"
        for b in ch.get("blocks", []):
            t = b.get("t")
            if t == "prose":
                yield f"{title} (prose)", b.get("tex", "")
            elif t == "stmt":
                ref = b.get("label") or b.get("title") or "?"
                yield f"{title} / {ref}", b.get("body", "")
            elif t == "proof":
                yield f"{title} (proof)", b.get("tex", "")


def check_katex(chapters: list[dict], macros: dict, *, timeout: int = 120) -> list[str]:
    """Return one ``"<ref>: KaTeX parse error: <message> in \"<snippet>\""`` string
    per math span that real KaTeX rejects. ``[]`` if Node/katex isn't installed —
    callers should treat that the same as "no errors found", not "unavailable"."""
    if not katex_available():
        return []
    items = [{"ref": ref, "text": text} for ref, text in _iter_text_blocks(chapters)]
    if not items:
        return []
    payload = json.dumps({"items": items, "macros": macros})
    try:
        r = subprocess.run(
            ["node", str(_JS)], input=payload, capture_output=True, text=True,
            timeout=timeout, env={**os.environ, "NODE_PATH": _NODE_MODULES},
        )
        result = json.loads(r.stdout)
    except Exception as e:
        return [f"KaTeX validation could not run ({e}); math errors may be silently present"]
    out = []
    for e in result.get("errors", []):
        snippet = e["content"].replace("\n", " ").strip()
        out.append(f"{e['ref']}: KaTeX parse error: {e['message']} in \"{snippet}\"")
    return out
