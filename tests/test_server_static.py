import tempfile
import unittest
from pathlib import Path

from hgraph.server import _static_asset, _static_mounts


class StaticMountTests(unittest.TestCase):
    def test_resolves_index_and_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app = base / "dist"
            (app / "assets").mkdir(parents=True)
            (app / "index.html").write_text("<h1>map</h1>", encoding="utf-8")
            (app / "assets" / "app.js").write_text("export {};", encoding="utf-8")
            mounts = _static_mounts({"static": {"proof-map": "dist"}}, base)

            body, ctype, cache = _static_asset(mounts, "/proof-map/")
            self.assertEqual(body, b"<h1>map</h1>")
            self.assertEqual(ctype, "text/html")
            self.assertEqual(cache, "no-cache")

            body, ctype, cache = _static_asset(mounts, "/proof-map/assets/app.js")
            self.assertEqual(body, b"export {};")
            self.assertIn("javascript", ctype)
            self.assertIn("immutable", cache)

    def test_rejects_path_traversal_and_reserved_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "dist").mkdir()
            mounts = _static_mounts({"static": {"proof-map": "dist"}}, base)
            self.assertIsNone(_static_asset(mounts, "/proof-map/%2e%2e/secret"))
            with self.assertRaises(ValueError):
                _static_mounts({"static": {"assets": "dist"}}, base)


if __name__ == "__main__":
    unittest.main()
