from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

import hgraph.cli as cli
from hgraph.cli import main
from hgraph.graph import Graph, node_id
from hgraph.sync import project_sync_status, sync_from_config


def _await_serve_preflight() -> None:
    """`hgraph serve` runs its staleness check in a daemon thread so the server
    binds immediately; join it so the warning output is complete before asserting."""
    th = cli._LAST_SERVE_PREFLIGHT
    if th is not None:
        th.join(timeout=10)


BLUEPRINT = r"""
\begin{document}
\begin{theorem}[First]
\label{first}
The first statement.
\end{theorem}
\end{document}
"""

BLUEPRINT_WITH_MISSING_LEAN = r"""
\begin{document}
\begin{theorem}[Missing declarations]
\label{missing}
\lean{Missing.one, Missing.two, Missing.three, Missing.four, Missing.five}
This statement names declarations outside the scanned sources.
\end{theorem}
\end{document}
"""


class WorkspaceSyncTests(unittest.TestCase):
    def make_project(self, workspace: Path, name: str, body: str = BLUEPRINT) -> Path:
        root = workspace / name
        (root / "blueprint").mkdir(parents=True)
        (root / "hgraph").mkdir()
        (root / "blueprint" / "blueprint.tex").write_text(body, encoding="utf-8")
        (root / "hgraph" / "config.yaml").write_text(
            "blueprint: blueprint/blueprint.tex\n", encoding="utf-8")
        return root

    def write_manifest(self, workspace: Path, names: tuple[str, ...]) -> None:
        data = {"title": "Test workspace",
                "projects": [{"name": name.title(), "root": name} for name in names]}
        (workspace / "config.yaml").write_text(
            yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    def test_bare_sync_updates_every_workspace_project(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            roots = [self.make_project(workspace, name) for name in ("one", "two")]
            self.write_manifest(workspace, ("one", "two"))

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["--root", str(workspace), "sync"])

            self.assertEqual(code, 0)
            self.assertIn("2 synced, 0 skipped, 0 failed", stdout.getvalue())
            for root in roots:
                self.assertTrue(Graph.open(root).has_node(node_id("bp", "first")))

    def test_status_uses_sync_rules_without_writing(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_project(Path(td), "project")
            sync_from_config(root)
            node_path = root / "hgraph" / "nodes" / f"{node_id('bp', 'first')}.md"
            before = node_path.read_bytes()

            source = root / "blueprint" / "blueprint.tex"
            source.write_text(BLUEPRINT.replace("first statement", "changed statement"),
                              encoding="utf-8")
            status = project_sync_status(root)

            self.assertEqual(status["state"], "out_of_sync")
            self.assertGreater(status["result"]["changes"], 0)
            self.assertEqual(node_path.read_bytes(), before)

            sync_from_config(root)
            self.assertEqual(project_sync_status(root)["state"], "in_sync")

    def test_workspace_serve_warns_and_suggests_workspace_sync(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            root = self.make_project(workspace, "one")
            self.write_manifest(workspace, ("one",))
            sync_from_config(root)
            source = root / "blueprint" / "blueprint.tex"
            source.write_text(BLUEPRINT.replace("First", "Updated"), encoding="utf-8")

            stderr = io.StringIO()
            with mock.patch("hgraph.server.serve_workspace") as serve, \
                    contextlib.redirect_stderr(stderr):
                code = main(["--root", str(workspace), "serve"])
                _await_serve_preflight()

            self.assertEqual(code, 0)
            serve.assert_called_once()
            warning = stderr.getvalue()
            self.assertIn("One (one):", warning)
            self.assertIn("generated graph change(s) pending", warning)
            self.assertIn(f"hgraph --root {workspace} sync", warning)

    def test_sync_groups_warnings_and_verbose_expands_them(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_project(Path(td), "project", BLUEPRINT_WITH_MISSING_LEAN)

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["--root", str(root), "sync", "--color", "never"])

            self.assertEqual(code, 0)
            report = stdout.getvalue()
            self.assertIn("5 Lean references not found in scanned sources", report)
            self.assertIn("no Lean declarations scanned", report)
            self.assertIn("Missing.three", report)
            self.assertNotIn("Missing.four", report)
            self.assertIn("2 more; use --verbose to show all", report)

            verbose = io.StringIO()
            with contextlib.redirect_stdout(verbose):
                main(["--root", str(root), "sync", "--verbose", "--color", "always"])
            self.assertIn("Missing.five", verbose.getvalue())
            self.assertIn("\033[32m[synced]\033[0m", verbose.getvalue())

            preflight = io.StringIO()
            with mock.patch("hgraph.server.serve"), contextlib.redirect_stderr(preflight):
                main(["--root", str(root), "serve"])
                _await_serve_preflight()
            self.assertIn("5 Lean references not found in scanned sources",
                          preflight.getvalue())
            self.assertNotIn("Missing.four", preflight.getvalue())

    def test_workspace_failures_stay_in_the_ordered_report(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            self.make_project(workspace, "one", BLUEPRINT_WITH_MISSING_LEAN)
            bad = workspace / "bad" / "hgraph"
            bad.mkdir(parents=True)
            (bad / "config.yaml").write_text("lean: [MissingLean]\n", encoding="utf-8")
            self.write_manifest(workspace, ("one", "bad"))

            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["--root", str(workspace), "sync", "--color", "never"])

            self.assertEqual(code, 1)
            report = stdout.getvalue()
            self.assertLess(report.index("[synced] One"), report.index("[failed] Bad"))
            self.assertIn("Lean source path(s) not found", report)
            self.assertIn("1 failed, 5 warnings", report)
            self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
