from pathlib import Path
import tempfile
import unittest

from hgraph.dashboard import project_data, project_source, split_project_data
from hgraph.graph import Graph, HGraphError
from hgraph.site import build_site_data, project_progress, show_progress


class ProgressDisplayTests(unittest.TestCase):
    def test_opt_out_preserves_counts_and_reaches_static_and_live_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nodes = root / 'hgraph/nodes'
            nodes.mkdir(parents=True)
            (root / 'hgraph/config.yaml').write_text('site:\n  progress: false\n')
            for name, status in [('linked', 'lean_ok'), ('unlinked', 'empty')]:
                (nodes / f'{name}.md').write_text(
                    f'---\nid: {name}\ntype: tex\ngenerated: blueprint\nlean_status: {status}\n---\n')
            counts = project_progress(root)
            self.assertEqual(counts, dict(statements=2, done=1, partial=0, todo=1, pct=None))
            manifest = {'title': 'Workspace', 'projects': [{'name': 'P', 'root': '.'}]}
            card = build_site_data(manifest, base=root)['sections'][0]['projects'][0]
            self.assertIs(card['progress'], False)
            self.assertIsNone(card['stats']['pct'])
            graph = Graph.open(root)
            full = project_data(graph, title='P', root=root, include_layout=False)
            shell, _, _ = split_project_data(full)
            live = project_source(graph, title='P', root=root)
            for data in [full, shell, live['data'], live['shell']]:
                self.assertIs(data['progress'], False)
                self.assertEqual(len(data['entries']), 2)

    def test_default_and_explicit_true_keep_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertTrue(show_progress(root))
            self.assertEqual(project_progress(root)['pct'], 0)
            (root / 'hgraph').mkdir()
            (root / 'hgraph/config.yaml').write_text('site:\n  progress: true\n')
            self.assertTrue(show_progress(root))

    def test_rejects_ambiguous_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'hgraph').mkdir()
            (root / 'hgraph/config.yaml').write_text('site:\n  progress: "false"\n')
            with self.assertRaisesRegex(HGraphError, 'boolean'):
                show_progress(root)
