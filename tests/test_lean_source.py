import unittest

from hgraph.lean_source import keyword_count, scan_lean, statement_prefix
from hgraph.sync import parse_lean


class LeanSourceTests(unittest.TestCase):
    def test_comments_literals_and_docstrings(self):
        source = '''/-- Docs /- nested -/ sorry -/
/-! Module docs -/
-- axiom
def s := "sorry /- not a comment -/"
def r := r##"admit -- /-"##
def c := '"'
theorem good : True := by trivial -- sorry
theorem gap : True := by admit
'''
        scanned = scan_lean(source)
        self.assertEqual(len(scanned.code), len(source))
        self.assertEqual(scanned.code.count('\n'), source.count('\n'))
        self.assertEqual(keyword_count(scanned.code, 'sorry'), 0)
        self.assertEqual(keyword_count(scanned.code, 'admit'), 1)
        self.assertIn('-- axiom', scanned.without_docstrings)
        self.assertNotIn('Module docs', scanned.without_docstrings)
        self.assertIn('"sorry /- not a comment -/"', scanned.without_comments)

    def test_scopes_module_and_omit(self):
        decls = parse_lean('''module
public section
namespace Geometry
section
variable (p : Prop) [h : Decidable p]
omit h in
/-- The documentation. -/
public theorem first : True := by trivial
end
theorem second : True := by trivial
end
theorem outside : True := by trivial
end
''')
        self.assertEqual([d['fqname'] for d in decls],
                         ['Geometry.first', 'Geometry.second', 'outside'])
        self.assertIn('omit h in', decls[0]['context'])
        self.assertNotIn('omit h in', decls[1]['context'])
        self.assertEqual(decls[0]['doc'], 'The documentation.')
        self.assertEqual(decls[0]['statement'], 'public theorem first : True')

    def test_no_phantom_declaration_or_comment_admission(self):
        decls = parse_lean('''/-
namespace Fake
theorem fake : False := by sorry
-/
theorem real : True := by
  -- sorry is not needed
  trivial
''')
        self.assertEqual([d['fqname'] for d in decls], ['real'])
        self.assertFalse(decls[0]['sorry'])

    def test_statement_boundary_and_definition_body(self):
        source = 'theorem t (n : Nat := 0) : n = n := by rfl'
        self.assertEqual(statement_prefix(source, 'theorem'),
                         'theorem t (n : Nat := 0) : n = n')
        source = 'def f : Nat := 3'
        self.assertEqual(statement_prefix(source, 'def'), source)

    def test_inline_omit(self):
        decls = parse_lean('omit h in theorem t : True := by trivial')
        self.assertEqual(decls[0]['fqname'], 't')
        self.assertEqual(decls[0]['statement'], 'omit h in theorem t : True')

    def test_multiline_variable_context_and_module_docs(self):
        decls = parse_lean('/-! Module documentation -/\ntheorem first : True := by trivial\n'
                           'variable\n  (p : Prop)\n  [h : Decidable p]\n'
                           'theorem second : True := by trivial')
        self.assertEqual(decls[0]['doc'], '')
        self.assertIn('[h : Decidable p]', decls[1]['context'])
