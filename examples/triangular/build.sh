#!/usr/bin/env bash
# A second small example, alongside gauss — gauss demonstrates the *sync*
# workflow end to end; this one is built to exercise the schema fields gauss
# doesn't: more content_types, more origins, a stale-node demo, a related_to
# edge, and the two-axis (Maths/Lean) review shape.
#
# Run:  bash examples/triangular/build.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$(cd "$HERE/../.." && pwd)"
cd "$HERE"
rm -rf hgraph/nodes hgraph/edges   # start clean, but keep hgraph/config.yaml
hg() { python3 -m hgraph "$@"; }

echo "── 1. sync: parse the blueprint + Lean sources into the graph ──"
hg sync

echo; echo "── 2. content_type / origin / lang / status the .tex/.lean can't express ──"

# a textbook origin, with details, and the lang tag
hg modify node label:def:triangular \
   --set origin=textbook --set 'origin_details={work: Concrete Mathematics, chapter: Sums}' \
   --set lang=en

# lecture-notes / article / preprint — origins gauss's example doesn't use
hg modify node label:thm:triangular-closed-form  --set origin=lecture-notes
hg modify node label:prop:triangular-consecutive-sum --set origin=article
hg modify node label:cor:triangular-even-odd     --set origin=preprint --set status=built

# status: false (not yet started) on the worked example
hg modify node label:ex:triangular-five --set status=false

# the illustrative conjecture: origin unknown
hg modify node label:conj:square-triangular --set origin=unknown

# the Lean-only `instance` node (content_type=instance, no blueprint \lean{})
# — origin repository, since it lives only in the Lean source
hg modify node decl:Triangular.decidableIsTriangular --set origin=repository

echo; echo "── 3. two hand-added nodes + a related_to edge ──"

# (a) a source quote — content_type=quote, distinct from a statement node
hg add node --title "Triangular numbers, Concrete Mathematics" --type tex --key triangular-quote \
   --content-type quote --author human --origin textbook \
   --content 'The n-th triangular number is the number of dots that can be arranged in a triangle with n dots on a side.'

# (b) a hand-written alternative proof — content_type=proof, origin=ai,
#     linked to the theorem it re-proves by a related_to edge (associative,
#     not a dependency — the theorem doesn't need this node to be closed)
hg add node --title "Combinatorial proof of the closed form" --type tex --key triangular-alt-proof \
   --content-type proof --author agent --origin ai --set status=built \
   --content 'Count pairs (i, j) with 1 <= i <= j <= n in two ways: n(n+1)/2 directly, or as T_n.'
hg add edge key:triangular-alt-proof label:thm:triangular-closed-form --type related_to

echo; echo "── 4. reviews — Maths good/bad and Lean good/bad, independently ──"

# a full review: both axes set
hg add review label:thm:triangular-closed-form --author reviewer \
   --maths good --maths-comment 'statement and proof sketch are both correct.' \
   --lean good --lean-comment 'closed_form has no sorry — fully checked.'

# a single-axis review: maths only (no Lean side to judge yet)
hg add review label:cor:triangular-even-odd --author human \
   --maths bad --maths-comment 'the residue classes need a cleaner case split.'

echo; echo "── 5. sync AGAIN — idempotency check, as in the gauss example ──"
hg sync

echo; echo "── 6. stale-node demo: sync WITH an extra label, then WITHOUT it ──"
# a throwaway blueprint copy with one more labeled statement the real source
# doesn't have — appended in-place (this project's blueprint is a single flat
# .tex with no \input, so a sibling temp file resolves fine)
STALE_DEMO="$HERE/blueprint/_stale_demo.tex"
head -n -1 blueprint/blueprint.tex > "$STALE_DEMO"   # everything but \end{document}
cat >> "$STALE_DEMO" <<'EOF'
\begin{lemma}[Scratch placeholder]\label{lem:scratch-demo}
This statement exists only to demonstrate `stale`: present in this sync,
gone in the next one.
\end{lemma}
\end{document}
EOF
hg sync --blueprint "$STALE_DEMO" --lean Lean
echo "  (lem:scratch-demo now exists)"
rm -f "$STALE_DEMO"
hg sync   # the real sync, from hgraph/config.yaml — the extra label is gone
echo "  (lem:scratch-demo's label vanished — it should now show as stale)"
hg list --stale

echo; echo "════════ stats (closure + provenance breakdown) ════════"
hg stats

echo; echo "════════ the Lean-only instance node ════════"
hg get decl:Triangular.decidableIsTriangular

echo; echo "════════ the theorem: both review axes ════════"
hg get label:thm:triangular-closed-form

echo; echo "── 7. the site — one command, project view included, even solo ──"
# Everything generated goes under _site/ (gitignored): the example dir itself
# holds only sources. The workspace build at the repo root (`hgraph site`, see
# ../../config.yaml) renders this project too and is what GitHub Pages deploys —
# this solo page is just the "a lone project needs no manifest" demo.
hg site --out _site/index.html

echo; echo "view it:"
echo "  open directly:   xdg-open $HERE/_site/index.html"
echo "  or serve a dir:  (cd $HERE/_site && python -m http.server 8000)  → http://localhost:8000/"
echo "  the whole workspace: (cd $(cd "$HERE/../.." && pwd) && hgraph serve)"
