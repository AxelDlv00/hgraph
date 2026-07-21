from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hgraph.cli import main
from hgraph.collaboration import _git_blob_sha, collect_pending, send_review_batch
from hgraph.graph import Graph


class CollaborationTests(unittest.TestCase):
    def make_project(self, parent: Path) -> tuple[Path, str]:
        root = parent / "project"
        (root / "hgraph" / "nodes").mkdir(parents=True)
        (root / "hgraph" / "config.yaml").write_text(
            "site:\n  title: Test Blueprint\n  repo: owner/repo\n", encoding="utf-8")
        graph = Graph.open(root)
        node_id = graph.add_node(
            "Pythagoras", type="tex", id="pythagoras", label="thm:pythagoras",
            content_type="theorem", chapter="Geometry", ref="I.47")
        graph.add_attachment(
            node_id, "review", "The proof could cite the preceding lemma.",
            author="Ada", maths_verdict="good", maths_comment="Correct.",
            lean_verdict="bad", lean_comment="The theorem is still a placeholder.")
        graph.add_attachment(
            node_id, "comment", "Please clarify the equality case.",
            author="Emmy", title="Equality case")
        return root, node_id

    @staticmethod
    def fake_run(root: Path, *, remote_tree: list[dict] | None = None,
                 calls: list | None = None):
        tree = remote_tree or []

        def run(args, *, cwd, input_text=None):
            if calls is not None:
                calls.append((list(args), Path(cwd), input_text))
            if args == ["git", "rev-parse", "--show-toplevel"]:
                return str(root)
            if args == ["git", "rev-parse", "HEAD"]:
                return "0123456789abcdef"
            if args[:2] == ["gh", "api"]:
                return json.dumps({"tree": tree, "truncated": False})
            if args[:3] == ["gh", "issue", "create"]:
                return "https://github.com/owner/repo/issues/42"
            if args[:3] == ["gh", "issue", "comment"]:
                return "https://github.com/owner/repo/issues/42#issuecomment-1"
            raise AssertionError(f"unexpected command: {args}")

        return run

    def test_send_creates_one_issue_and_one_comment_per_attachment(self):
        with tempfile.TemporaryDirectory() as td:
            root, _ = self.make_project(Path(td))
            calls: list = []
            with mock.patch("hgraph.collaboration.shutil.which", return_value="/usr/bin/gh"), \
                    mock.patch("hgraph.collaboration._run",
                               side_effect=self.fake_run(root, calls=calls)):
                result = send_review_batch(
                    root, repo="owner/repo", base="main", labels=["review"])

            self.assertEqual(result["issue"], "https://github.com/owner/repo/issues/42")
            self.assertEqual(len(result["pending"]), 2)
            creates = [call for call in calls if call[0][:3] == ["gh", "issue", "create"]]
            comments = [call for call in calls if call[0][:3] == ["gh", "issue", "comment"]]
            self.assertEqual(len(creates), 1)
            self.assertEqual(len(comments), 2)
            self.assertIn("--label", creates[0][0])
            self.assertIn("thm:pythagoras", creates[0][2])
            rendered = "\n".join(call[2] for call in comments)
            self.assertIn("**Verdict:** good", rendered)
            self.assertIn("The theorem is still a placeholder.", rendered)
            self.assertIn("Please clarify the equality case.", rendered)

    def test_identical_remote_attachment_is_not_pending(self):
        with tempfile.TemporaryDirectory() as td:
            root, node_id = self.make_project(Path(td))
            review = root / "hgraph" / "nodes" / node_id / "review-1.md"
            tree = [{
                "path": review.relative_to(root).as_posix(),
                "type": "blob",
                "sha": _git_blob_sha(review.read_bytes()),
            }]
            with mock.patch("hgraph.collaboration.shutil.which", return_value="/usr/bin/gh"), \
                    mock.patch("hgraph.collaboration._run",
                               side_effect=self.fake_run(root, remote_tree=tree)):
                _, _, _, pending = collect_pending(
                    root, repo="owner/repo", base="main", kinds={"review", "comment"})

            self.assertEqual([attachment.kind for attachment in pending], ["comment"])

    def test_cli_dry_run_prints_template_without_writing_to_github(self):
        with tempfile.TemporaryDirectory() as td:
            root, _ = self.make_project(Path(td))
            calls: list = []
            stdout = io.StringIO()
            with mock.patch("hgraph.collaboration.shutil.which", return_value="/usr/bin/gh"), \
                    mock.patch("hgraph.collaboration._run",
                               side_effect=self.fake_run(root, calls=calls)), \
                    contextlib.redirect_stdout(stdout):
                code = main(["--root", str(root), "review", "send", "--dry-run",
                             "--reviews-only", "--repo", "owner/repo", "--base", "main"])

            self.assertEqual(code, 0)
            output = stdout.getvalue()
            self.assertIn("ISSUE BODY", output)
            self.assertIn("ISSUE COMMENT 1/1", output)
            self.assertIn("Review: Pythagoras", output)
            self.assertFalse(any(call[0][:2] == ["gh", "issue"] for call in calls))


if __name__ == "__main__":
    unittest.main()
