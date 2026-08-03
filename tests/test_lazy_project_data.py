from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hgraph.dashboard import (hydrate_project_chapter, hydrate_project_entries,
                              project_source, split_project_data)
from hgraph.graph import Graph
from hgraph.site import write_static_site


def _entry() -> dict:
    return {
        "id": "node-1", "label": "thm:one", "title": "One", "chapter": "1",
        "kind": "theorem", "level": "medium", "ref": None, "sketch": False,
        "body": "A deliberately large statement body.", "lean_status": "sorry",
        "mathlib_name": None, "status": None, "tags": ["main"],
        "lean": [{"name": "Project.one", "status": "sorry", "file": "P.lean",
                  "code": "theorem one := by sorry"}],
        "deps": [], "reviewed": True, "maths_verdict": "good", "lean_verdict": None,
        "reviews": [{"maths_verdict": "good"}], "comments": [{"text": "note"}],
    }


def _project_data() -> dict:
    entry = _entry()
    return {
        "title": "Project", "mode": "doc", "entries": [entry],
        "chapters": [{
            "title": "First", "num": "1", "blocks": [
                {"t": "head", "level": 2, "title": "Start", "num": "1.1"},
                {"t": "prose", "tex": "Large introductory prose."},
                {"t": "stmt", "label": "thm:one", "labels": ["thm:one"],
                 "title": "One", "content_type": "theorem", "lean": [], "uses": [],
                 "leanok": False, "mathlibok": False, "body": entry["body"],
                 "num": "1.1", "abbr": "Thm", "id": "node-1",
                 "enrich": {**entry, "lean_status": "sorry"}},
                {"t": "proof", "tex": "A long proof."},
            ],
        }],
        "refs": {"thm:one": {"num": "1.1", "id": "node-1", "abbr": "Thm",
                               "kind": "stmt", "ch": 0, "anchor": "stmt-node-1"}},
        "loc": {"node-1": 0}, "bib": [], "docTitle": "Project", "docAuthor": None,
        "macros": {}, "repo": None, "theme": None, "customTabs": [],
        "gvsvg": {"overview": "<svg>layout</svg>"},
        "extrefs": {"Other": {"root": "other", "name": "Other", "refs": {}}},
    }


class SplitProjectDataTests(unittest.TestCase):
    def test_shell_keeps_outline_and_defers_heavy_content(self):
        data = _project_data()
        shell, chapters, graph = split_project_data(data)

        self.assertEqual(shell["lazy"]["chapters"], "chapters/{index}.json")
        self.assertNotIn("gvsvg", shell)
        self.assertNotIn("extrefs", shell)
        self.assertEqual([b["t"] for b in shell["chapters"][0]["blocks"]],
                         ["head", "stmt"])
        self.assertEqual(shell["chapters"][0]["blocks"][1]["body"], "")
        self.assertEqual(shell["entries"][0]["body"], "")
        self.assertEqual(shell["entries"][0]["lean"][0]["name"], "Project.one")
        self.assertEqual(shell["entries"][0]["lean"][0]["code"], "")

        self.assertEqual(chapters[0]["blocks"][1]["tex"], "Large introductory prose.")
        self.assertEqual(graph["entries"][0]["body"], data["entries"][0]["body"])
        self.assertIn("overview", graph["gvsvg"])
        self.assertEqual(data["chapters"][0]["blocks"][2]["body"],
                         "A deliberately large statement body.")

    def test_static_export_writes_lazy_files_and_compatibility_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "workspace"
            out = Path(tmp) / "site" / "index.html"
            (base / "proj").mkdir(parents=True)
            manifest = {"title": "Workspace", "projects": [{"name": "P", "root": "proj"}]}
            with patch("hgraph.dashboard.project_data", return_value=_project_data()):
                write_static_site(manifest, base=base, out_path=out)

            root = out.parent / "proj"
            for name in ("data.json", "project.json", "graph.json", "extrefs.json",
                         "chapters/0.json"):
                self.assertTrue((root / name).is_file(), name)
            shell = json.loads((root / "project.json").read_text(encoding="utf-8"))
            chapter = json.loads((root / "chapters/0.json").read_text(encoding="utf-8"))
            self.assertEqual(shell["entries"][0]["body"], "")
            self.assertEqual(chapter["blocks"][2]["body"],
                             "A deliberately large statement body.")

    def test_live_shell_does_not_read_attachments_or_full_lean_source(self):
        root = Path(__file__).resolve().parents[1] / "examples" / "gauss"
        graph = Graph.open(root)
        with patch.object(graph, "attachments", side_effect=AssertionError("eager attachments")):
            project = project_source(graph, title="Gauss", root=str(root))

        self.assertTrue(project["shell"]["chapters"])
        self.assertTrue(all(entry["body"] == "" for entry in project["shell"]["entries"]))
        self.assertTrue(all(item["code"] == "" for entry in project["shell"]["entries"]
                            for item in entry["lean"]))

        with patch.object(graph, "attachments", wraps=graph.attachments) as attachments:
            chapter = hydrate_project_chapter(project, graph, 0)
            entries = hydrate_project_entries(project, graph)
        self.assertGreater(attachments.call_count, 0)
        self.assertTrue(any(block.get("body") for block in chapter["blocks"]
                            if block["t"] == "stmt"))
        self.assertTrue(any(entry["body"] for entry in entries))


if __name__ == "__main__":
    unittest.main()
