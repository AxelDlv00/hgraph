from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hgraph.dashboard import (
    _resolve_blueprint,
    build_document,
    project_data,
    resolve_extrefs,
)
from hgraph.graph import Graph
from hgraph.site import _project_handle, build_extref_index
from hgraph.sync import sync_from_config

BETA = r"""
\begin{document}
\chapter{Main}
\begin{theorem}[Closed form]\label{thm:closed}\lean{Beta.closed}\leanok
A closed form.
\end{theorem}
\end{document}
"""

ALPHA = r"""
\begin{document}
\chapter{Main}
\begin{theorem}[Uses beta]\label{thm:alpha}\lean{Alpha.main}
This relies on \citeext{beta}{thm:closed}, from another blueprint
\citeext{beta}.
\end{theorem}
\end{document}
"""


class HandleTests(unittest.TestCase):
    def test_basename_of_root(self):
        self.assertEqual(_project_handle({"root": "formalized-sources/DoCarmo"}), "DoCarmo")
        self.assertEqual(_project_handle({"root": "gauss/"}), "gauss")

    def test_key_override(self):
        self.assertEqual(_project_handle({"root": "x/DoCarmo", "key": "docarmo"}), "docarmo")


class ResolveExtrefsTests(unittest.TestCase):
    def _index(self):
        return {"beta": {"root": "examples/beta", "name": "Beta",
                         "refs": {"thm:closed": {"num": "1.2", "abbr": "Thm"}}}}

    def test_labeled_and_bare(self):
        chapters = [{"blocks": [
            {"t": "stmt", "body": "see \\citeext{beta}{thm:closed}"},
            {"t": "prose", "tex": "also \\citeext{beta} in general"},
        ]}]
        out = resolve_extrefs(chapters, self._index())
        self.assertEqual(out["beta"]["root"], "examples/beta")
        self.assertEqual(out["beta"]["name"], "Beta")
        self.assertEqual(out["beta"]["refs"]["thm:closed"], {"num": "1.2", "abbr": "Thm"})

    def test_unknown_handle_is_omitted(self):
        chapters = [{"blocks": [{"t": "prose", "tex": "\\citeext{ghost}{x}"}]}]
        self.assertEqual(resolve_extrefs(chapters, self._index()), {})

    def test_known_handle_unknown_label_keeps_project_without_ref(self):
        chapters = [{"blocks": [{"t": "prose", "tex": "\\citeext{beta}{nope}"}]}]
        out = resolve_extrefs(chapters, self._index())
        self.assertIn("beta", out)              # link still works (root/name present)
        self.assertEqual(out["beta"]["refs"], {})  # but no number was baked

    def test_no_citeext_is_empty(self):
        chapters = [{"blocks": [{"t": "prose", "tex": "plain \\cref{thm:x} text"}]}]
        self.assertEqual(resolve_extrefs(chapters, self._index()), {})


class IntegrationTests(unittest.TestCase):
    def _project(self, ws: Path, name: str, bp: str) -> Path:
        root = ws / name
        (root / "blueprint").mkdir(parents=True)
        (root / "hgraph").mkdir()
        (root / "blueprint" / "blueprint.tex").write_text(bp, encoding="utf-8")
        (root / "hgraph" / "config.yaml").write_text(
            "blueprint: blueprint/blueprint.tex\n", encoding="utf-8")
        sync_from_config(root)
        return root

    def test_cross_project_citation_resolves_to_siblings_number(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            self._project(ws, "alpha", ALPHA)
            self._project(ws, "beta", BETA)
            manifest = {"projects": [{"name": "Alpha", "root": "alpha"},
                                     {"name": "Beta", "root": "beta"}]}

            index = build_extref_index(manifest, ws)
            self.assertIn("thm:closed", index["beta"]["refs"])

            g = Graph.open(str(ws / "alpha"))
            doc = build_document(g, _resolve_blueprint(None, str(ws / "alpha")), title="Alpha")
            ext = resolve_extrefs(doc["chapters"], index)

            self.assertEqual(ext["beta"]["root"], "beta")
            self.assertEqual(ext["beta"]["name"], "Beta")
            target = ext["beta"]["refs"]["thm:closed"]
            self.assertTrue(target["num"])            # a real number was resolved
            self.assertEqual(target["abbr"], "Thm")

    def test_solo_build_leaves_citeext_unresolved_without_crashing(self):
        # alpha alone: \citeext{beta}{...} has no sibling to resolve against
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            self._project(ws, "alpha", ALPHA)
            index = build_extref_index({"projects": [{"name": "Alpha", "root": "alpha"}]}, ws)
            g = Graph.open(str(ws / "alpha"))
            doc = build_document(g, _resolve_blueprint(None, str(ws / "alpha")), title="Alpha")
            self.assertEqual(resolve_extrefs(doc["chapters"], index), {})


if __name__ == "__main__":
    unittest.main()
