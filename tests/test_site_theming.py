from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from hgraph.graph import HGraphError
from hgraph.site import (
    _content_tabs,
    _derive_theme,
    _norm_hex,
    _resolve_theme,
    _theme_of,
    build_site_data,
)

_THEME_FIELDS = ("accent", "accentDark", "gradientFrom", "gradientTo", "pillBg", "pillText")


class NormHexTests(unittest.TestCase):
    def test_expands_shorthand_and_lowercases(self):
        self.assertEqual(_norm_hex("#ABC"), "#aabbcc")
        self.assertEqual(_norm_hex("  #B4530B "), "#b4530b")

    def test_rejects_non_hex(self):
        for bad in ("red", "#12", "#1234", "4938D1", "#gggggg"):
            with self.assertRaises(HGraphError):
                _norm_hex(bad)


class DeriveThemeTests(unittest.TestCase):
    def test_full_theme_from_one_accent(self):
        t = _derive_theme("#B4530B")
        self.assertEqual(set(t), set(_THEME_FIELDS))
        # accent preserved (normalised); pill text mirrors it; every field a hex
        self.assertEqual(t["accent"], "#b4530b")
        self.assertEqual(t["pillText"], "#b4530b")
        self.assertEqual(t["pillBg"], t["gradientFrom"])  # matches theme.ts's THEMES
        for v in t.values():
            self.assertRegex(v, r"^#[0-9a-f]{6}$")

    def test_derived_tints_are_light_and_dark(self):
        t = _derive_theme("#4938D1")
        # gradient/pill are near-white tints; accentDark is darker than the accent
        self.assertGreater(int(t["gradientFrom"][1:], 16), int(t["accent"][1:], 16))
        self.assertLess(sum(int(t["accentDark"][i:i + 2], 16) for i in (1, 3, 5)),
                        sum(int(t["accent"][i:i + 2], 16) for i in (1, 3, 5)))


class ThemeOfTests(unittest.TestCase):
    def test_accent_shorthand(self):
        self.assertEqual(_theme_of({"accent": "#B4530B"}), {"accent": "#b4530b"})

    def test_partial_theme_block(self):
        out = _theme_of({"theme": {"accent": "#058476", "pillText": "#058476"}})
        self.assertEqual(out, {"accent": "#058476", "pillText": "#058476"})

    def test_nothing_configured(self):
        self.assertEqual(_theme_of({}), {})

    def test_theme_block_must_be_mapping(self):
        with self.assertRaises(HGraphError):
            _theme_of({"theme": "#058476"})


class ResolveThemeTests(unittest.TestCase):
    def _project(self, parent: Path, site: dict | None = None) -> Path:
        root = Path(tempfile.mkdtemp(dir=parent))
        (root / "hgraph").mkdir()
        import yaml
        cfg = {"site": site} if site else {}
        (root / "hgraph" / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
        return root

    def test_none_when_unconfigured(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = self._project(base)
            self.assertIsNone(_resolve_theme({"root": root.name}, {}, base))

    def test_global_default_applies(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = self._project(base)
            t = _resolve_theme({"root": root.name}, {"theme": {"accent": "#058476"}}, base)
            self.assertEqual(t["accent"], "#058476")

    def test_project_own_config_overrides_global(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = self._project(base, site={"accent": "#B4530B"})
            t = _resolve_theme({"root": root.name}, {"accent": "#058476"}, base)
            self.assertEqual(t["accent"], "#b4530b")

    def test_manifest_entry_wins_over_project_config(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = self._project(base, site={"accent": "#B4530B"})
            t = _resolve_theme({"root": root.name, "accent": "#111111"},
                               {"accent": "#058476"}, base)
            self.assertEqual(t["accent"], "#111111")

    def test_explicit_theme_field_overrides_derived(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = self._project(base)
            t = _resolve_theme(
                {"root": root.name, "accent": "#B4530B", "theme": {"pillBg": "#ffffff"}},
                {}, base)
            self.assertEqual(t["accent"], "#b4530b")   # from shorthand
            self.assertEqual(t["pillBg"], "#ffffff")   # explicit field wins

    def test_bad_hex_raises(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = self._project(base)
            with self.assertRaises(HGraphError):
                _resolve_theme({"root": root.name, "accent": "not-a-colour"}, {}, base)


class ContentTabsTests(unittest.TestCase):
    def test_resolves_md_and_html(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "people.md").write_text("# People\n\nHello", encoding="utf-8")
            (base / "roadmap.html").write_text("<p>Soon</p>", encoding="utf-8")
            tabs = _content_tabs(
                [{"id": "people", "label": "People", "content": "people.md"},
                 {"id": "roadmap", "label": "Roadmap", "content": "roadmap.html", "icon": "map"}],
                base=base, where="manifest")
            self.assertEqual([t["id"] for t in tabs], ["people", "roadmap"])
            self.assertIn("<h3>People</h3>", tabs[0]["html"])   # md converted
            self.assertEqual(tabs[1]["html"], "<p>Soon</p>")     # html verbatim
            self.assertEqual(tabs[1]["icon"], "map")

    def test_missing_file_warns_and_skips(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                tabs = _content_tabs(
                    [{"id": "gone", "label": "Gone", "content": "nope.md"}],
                    base=base, where="manifest")
            self.assertEqual(tabs, [])
            self.assertIn("not found", buf.getvalue())

    def test_malformed_entries_raise(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            for bad in ([{"label": "No id", "content": "x.md"}],
                        [{"id": "x", "content": "x.md"}],
                        [{"id": "x", "label": "X"}],
                        "not a list"):
                with self.assertRaises(HGraphError):
                    _content_tabs(bad, base=base, where="manifest")

    def test_empty_is_empty(self):
        self.assertEqual(_content_tabs(None, base=Path("."), where="manifest"), [])


class BuildSiteDataTests(unittest.TestCase):
    def test_carries_tabs_and_theme(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "people.md").write_text("# People", encoding="utf-8")
            (base / "proj").mkdir()
            manifest = {
                "title": "T",
                "tabs": [{"id": "people", "label": "People", "content": "people.md"}],
                "theme": {"accent": "#058476"},
                "projects": [{"name": "P", "root": "proj"}],
            }
            data = build_site_data(manifest, base=base)
            self.assertEqual([t["id"] for t in data["tabs"]], ["people"])
            card = data["sections"][0]["projects"][0]
            self.assertEqual(card["theme"]["accent"], "#058476")   # global default
            self.assertEqual(data["sections"][0]["theme"]["accent"], "#058476")

    def test_no_config_means_no_theme(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "proj").mkdir()
            manifest = {"title": "T", "projects": [{"name": "P", "root": "proj"}]}
            data = build_site_data(manifest, base=base)
            self.assertIsNone(data["sections"][0]["projects"][0]["theme"])
            self.assertEqual(data["tabs"], [])


if __name__ == "__main__":
    unittest.main()
