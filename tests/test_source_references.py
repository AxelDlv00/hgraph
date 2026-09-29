import unittest

from hgraph.sync import parse_blueprint


class SourceReferenceTests(unittest.TestCase):
    def test_repeated_references_are_retained_without_splitting_commas(self):
        statements, _ = parse_blueprint(r"""
\begin{theorem}\label{thm:a}
\dcref{Definitions 6.1--6.2, p. 106}
\dcref{Theorem 6.80, pp. 145--146}
\source{ignored fallback}
A statement.
\end{theorem}
""")
        self.assertEqual(statements[0]["ref"],
                         "Definitions 6.1--6.2, p. 106; Theorem 6.80, pp. 145--146")

    def test_source_fallback_keeps_multiple_coordinates(self):
        statements, _ = parse_blueprint(r"""
\begin{lemma}\label{lem:a}\source{Book, p. 1}\source{Book, p. 2}
A statement.\end{lemma}
""")
        self.assertEqual(statements[0]["ref"], "Book, p. 1; Book, p. 2")
