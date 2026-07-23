import unittest

from hgraph.dashboard import number_document
from hgraph.sync import _assoc_proofs, parse_blueprint, parse_document

# A blueprint whose entry file \input{macros} instead of wrapping its body in
# \begin{document}: the macro definitions sit inline, ahead of the first chapter.
PREAMBLE = r"""
\newcommand{\R}{\mathbb{R}}
\newcommand\C{\mathbb{C}}
\newcommand[1]{\Sph}{S^{#1}}
\DeclareMathOperator{\grad}{grad}
\newtheorem{thm}[theorem]{Theorem}[section]
"""

DOC = PREAMBLE + r"""
\chapter{What Is Curvature?}
\label{chap:what-is-curvature}
Plane curves bend.

\section{Plane curves}
\begin{definition}[Curvature]\label{def:curvature}
The curvature is $\kappa$.
\end{definition}

\section*{Notes}
An unnumbered aside.

\chapter[Metrics]{Riemannian Metrics}
\begin{lemma}\label{lem:metric}A lemma.\end{lemma}

\chapter*{Preface}
Front matter.

\appendix

\chapter{Review of Smooth Manifolds}
\begin{theorem}\label{thm:smooth}An appendix theorem.\end{theorem}
\section{Topology}

\chapter{Review of Tensors}
\begin{theorem}\label{thm:tensors}Another one.\end{theorem}
"""


EQUATIONS = r"""
\chapter{Curvature}
\label{chap:curvature}

\section{Plane curves}
\label{sec:plane-curves}
The curvature satisfies
\begin{equation}\label{eq:kappa}
  \kappa = \frac{d\theta}{ds}.
\end{equation}
and the Frenet equations are
\begin{align}
  T' &= \kappa N \label{eq:frenet} \\
  N' &= -\kappa T \nonumber \\
  B' &= \tau N \label{eq:frenet-b}
\end{align}

\begin{definition}[Convexity]\label{def:convex}
A curve with
\begin{equation}\label{eq:positive}
  \kappa > 0
\end{equation}
is convex.
\end{definition}

\begin{equation*}
  \text{never numbered}
\end{equation*}

\chapter{Next}
\begin{equation}\label{eq:next}
  a = b
\end{equation}
"""


def numbered(text: str) -> list[dict]:
    chapters = parse_document(text)
    number_document(chapters)
    return chapters


class DocumentStructureTests(unittest.TestCase):
    def test_preamble_does_not_become_a_chapter(self) -> None:
        # the macro file used to land in a phantom "Introduction" chapter
        self.assertEqual(parse_document(PREAMBLE), [])
        self.assertEqual(numbered(DOC)[0]["title"], "What Is Curvature?")

    def test_leading_prose_still_becomes_a_chapter(self) -> None:
        chapters = numbered(PREAMBLE + "\nReal introductory prose.\n\\chapter{One}\nBody.")
        self.assertEqual([ch["title"] for ch in chapters], ["Introduction", "One"])
        self.assertEqual(chapters[0]["blocks"],
                         [{"t": "prose", "tex": "Real introductory prose."}])

    def test_optional_short_title_is_not_swallowed(self) -> None:
        # \chapter[Short]{Long} used to match no heading at all, so the whole
        # chapter leaked into the previous one as prose
        titles = [ch["title"] for ch in numbered(DOC)]
        self.assertIn("Riemannian Metrics", titles)


class NumberingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.chapters = numbered(DOC)
        self.by_title = {ch["title"]: ch for ch in self.chapters}

    def nums(self, title: str) -> list:
        return [b["num"] for b in self.by_title[title]["blocks"]
                if b["t"] in ("head", "stmt")]

    def test_chapters_are_numbered_in_order(self) -> None:
        self.assertEqual(self.by_title["What Is Curvature?"]["num"], "1")
        self.assertEqual(self.by_title["Riemannian Metrics"]["num"], "2")

    def test_starred_chapter_is_unnumbered_and_skips_the_counter(self) -> None:
        self.assertIsNone(self.by_title["Preface"]["num"])
        # "Preface" sits between chapter 2 and the appendices, and takes no number
        self.assertEqual(self.by_title["Review of Smooth Manifolds"]["num"], "A")

    def test_starred_section_is_unnumbered_and_skips_the_counter(self) -> None:
        # \section{Plane curves} → 1.1, \section*{Notes} → none, def → 1.1
        self.assertEqual(self.nums("What Is Curvature?"), ["1.1", "1.1", None])

    def test_appendix_switches_to_letters(self) -> None:
        self.assertEqual(self.by_title["Review of Smooth Manifolds"]["num"], "A")
        self.assertEqual(self.by_title["Review of Tensors"]["num"], "B")
        self.assertEqual(self.nums("Review of Smooth Manifolds"), ["A.1", "A.1"])

    def test_appendix_chapters_are_flagged_for_the_toc(self) -> None:
        self.assertEqual([ch.get("appendix", False) for ch in self.chapters],
                         [False, False, False, True, True])

    def test_statements_under_an_unnumbered_chapter_drop_the_prefix(self) -> None:
        chapters = numbered("\\chapter*{Preface}\n"
                            "\\begin{remark}\\label{r}Note.\\end{remark}")
        self.assertEqual(chapters[0]["blocks"][0]["num"], "1")


class CrossReferenceTests(unittest.TestCase):
    """What `\\cref{…}` has to resolve beyond theorem-like statements."""

    def setUp(self) -> None:
        self.chapters = parse_document(EQUATIONS)
        self.refs = number_document(self.chapters)

    def blocks(self, ci: int) -> list[dict]:
        return self.chapters[ci]["blocks"]

    def test_chapter_and_section_labels_resolve(self) -> None:
        self.assertEqual(self.refs["chap:curvature"],
                         {"num": "1", "id": None, "abbr": "Chapter",
                          "kind": "chap", "ch": 0, "anchor": ""})
        self.assertEqual(self.refs["sec:plane-curves"],
                         {"num": "1.1", "id": None, "abbr": "Section",
                          "kind": "sec", "ch": 0, "anchor": "sec-1.1"})

    def test_equations_are_numbered_per_chapter(self) -> None:
        nums = {k: v["num"] for k, v in self.refs.items() if v["kind"] == "eq"}
        self.assertEqual(nums, {
            "eq:kappa": "1.1",       # \begin{equation}
            "eq:frenet": "1.2",      # first align row
            "eq:frenet-b": "1.3",    # third row — the \nonumber one took no number
            "eq:positive": "1.4",    # inside a statement, but same counter
            "eq:next": "2.1",        # the counter restarts with the chapter
        })

    def test_the_number_is_written_back_as_a_tag(self) -> None:
        # KaTeX renders \tag exactly where LaTeX puts the number, so what the
        # reader sees and what \cref resolves to cannot drift apart
        tex = "".join(b["tex"] for b in self.blocks(0) if b["t"] == "prose")
        for n in ("1.1", "1.2", "1.3"):
            self.assertIn("\\tag{%s}" % n, tex)
        stmt = next(b for b in self.blocks(0) if b["t"] == "stmt")
        self.assertIn("\\tag{1.4}", stmt["body"])

    def test_starred_environments_take_no_number(self) -> None:
        unnumbered = [b for b in self.blocks(0)
                      if b["t"] == "prose" and "never numbered" in b["tex"]]
        self.assertEqual(len(unnumbered), 1)
        self.assertNotIn("\\tag{", unnumbered[0]["tex"])

    def test_an_authors_own_tag_wins_and_consumes_no_number(self) -> None:
        chapters = parse_document(
            "\\chapter{C}\n"
            "\\begin{equation}\\tag{$\\star$}\\label{eq:star}x=y\\end{equation}\n"
            "\\begin{equation}\\label{eq:after}a=b\\end{equation}")
        refs = number_document(chapters)
        self.assertEqual(refs["eq:star"]["num"], "$\\star$")
        self.assertEqual(refs["eq:star"]["anchor"], "")   # not a usable element id
        self.assertEqual(refs["eq:after"]["num"], "1.1")

    def test_an_equation_label_is_not_mistaken_for_the_statements(self) -> None:
        stmt = next(b for b in self.blocks(0) if b["t"] == "stmt")
        self.assertEqual(stmt["label"], "def:convex")
        self.assertEqual(stmt["labels"], ["def:convex"])
        # …and it survives in the body, where the equation numbering needs it
        self.assertIn("\\label{eq:positive}", stmt["body"])


SKETCHES = r"""
\chapter{C}
\begin{lemma}\label{lem:sketched}A lemma.\end{lemma}
\begin{proof}\sketch Only the idea: induct on $n$.\end{proof}

\begin{theorem}\label{thm:full}A theorem.\end{theorem}
\begin{proof}\leanok A complete proof.\end{proof}

\begin{proposition}\label{prop:marked}\sketch Marked on the statement itself.\end{proposition}
"""


class SketchTests(unittest.TestCase):
    """`\\sketch` — the author's own "this gap is intentional" marker."""

    def setUp(self) -> None:
        self.blocks = parse_document(SKETCHES)[0]["blocks"]
        self.statements, proofs = parse_blueprint(SKETCHES)
        _assoc_proofs(self.statements, proofs)
        self.by_label = {s["label"]: s for s in self.statements}

    def test_a_sketched_proof_block_is_flagged(self) -> None:
        proofs = [b for b in self.blocks if b["t"] == "proof"]
        self.assertEqual([b.get("sketch") for b in proofs], [True, None])

    def test_the_marker_never_reaches_the_rendered_text(self) -> None:
        for b in self.blocks:
            self.assertNotIn("\\sketch", b.get("tex", "") + b.get("body", ""))

    def test_a_proofs_sketch_folds_onto_the_statement_it_proves(self) -> None:
        # same path \leanok takes, so the statement card can show it too
        self.assertTrue(self.by_label["lem:sketched"]["sketch"])
        self.assertFalse(self.by_label["thm:full"]["sketch"])

    def test_sketch_on_the_statement_itself_counts(self) -> None:
        self.assertTrue(self.by_label["prop:marked"]["sketch"])


if __name__ == "__main__":
    unittest.main()
