import unittest

from hgraph.sync import parse_lean


def names(source: str) -> set[str]:
    return {decl["fqname"] for decl in parse_lean(source)}


class LeanParserTests(unittest.TestCase):
    def test_indexes_structures_and_unicode_names(self) -> None:
        found = names(
            """
namespace MorganTianLib
structure IsLocalFlow where
  eta_pos : True
@[simp] theorem curvatureOperator_ιMulti : True := by trivial
end MorganTianLib
"""
        )
        self.assertIn("MorganTianLib.IsLocalFlow", found)
        self.assertIn("MorganTianLib.curvatureOperator_ιMulti", found)

    def test_resets_namespace_for_root_declarations(self) -> None:
        found = names(
            """
namespace MorganTianLib
theorem _root_.HasStrictFDerivAt.continuousAt_derivMap : True := by trivial
end MorganTianLib
"""
        )
        self.assertIn("HasStrictFDerivAt.continuousAt_derivMap", found)
        self.assertNotIn("MorganTianLib._root_.HasStrictFDerivAt.continuousAt_derivMap", found)
