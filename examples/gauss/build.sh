#!/usr/bin/env bash
# Build the Gauss graph the new way: the blueprint (.tex) and the Lean sources
# are the REFERENCE; `hgraph sync` parses them into nodes + edges. A human/agent
# then layers on the things those files cannot hold (a source, a failure note),
# and a second sync proves that re-syncing is idempotent and never stomps them.
#
# Run:  bash examples/gauss/build.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$(cd "$HERE/../.." && pwd)"
cd "$HERE"
rm -rf hgraph/nodes hgraph/edges   # start clean, but keep hgraph/config.yaml
hg() { python3 -m hgraph "$@"; }

echo "── 1. sync: parse the blueprint + Lean sources into the graph ──"
hg sync                            # no flags → reads hgraph/config.yaml for the paths
#   → blueprint nodes (keyed by \label), Lean nodes (keyed by fq-name),
#     formalizes edges (\lean), uses edges (statement/proof \uses, collapsed).
#   Note Gauss.isEven_zero becomes a Lean node with no blueprint match.

echo; echo "── 2. a human/agent layers on what the sources can't hold ──"

# (a) provenance — structured `origin` enum + nested `origin_details` (inline YAML)
hg modify node label:thm:gauss --set origin=book \
   --set 'origin_details={work: Concrete Mathematics, author: "Graham, Knuth, Patashnik", edition: 2, page: 51}'

# (b) authored workflow state + tags (sync never touches these)
hg modify node label:thm:gauss    --set status=draft    --set 'tags=[flagship, summation]'
hg modify node label:def:even     --set status=verified --set 'tags=[parity]'
hg modify node label:lem:mul-succ --set status=failed   --set 'tags=[parity, blocked]'

# (c) a source quote as its own node + an associative (non-dependency) edge.
#     --key gives it a stable hash id, addressable by key:even-quote.
hg add node --title "Consecutive-integer product is even" --type tex --key even-quote \
   --author human --origin book --set 'origin_details={work: Concrete Mathematics, page: 51}' \
   --set 'tags=[source]' \
   --content 'The product of consecutive integers is always even.'
hg add edge label:lem:mul-succ key:even-quote --type related_to

# (d) failure memory — two comments (a progression) on the still-sorried lemma
hg add comment decl:Gauss.isEven_mul_succ --author agent --title "first attempt" \
   --content 'induction n; simp [IsEven] leaves ∃ k, … = 2*k unsolved.'
hg add comment decl:Gauss.isEven_mul_succ --author agent --title "next idea" \
   --content 'case on Nat.even_or_odd n; the odd case makes n+1 even, then ring.'

# (e) reviews are two axes — Maths good/bad + comment, Lean good/bad + comment —
#     either or both may be set
hg add review decl:Gauss.isEven_mul_succ --author reviewer \
   --maths good --maths-comment 'the statement is exactly what we want.' \
   --lean bad --lean-comment 'proof is unfinished — needs the parity split.'
hg add review label:thm:gauss --author human \
   --maths good --maths-comment 'the flagship result — prioritise it.'

echo; echo "── 3. sync AGAIN — content is re-derived, all of the above survives ──"
hg sync

echo; echo "════════ get the sorried lemma's Lean side (2 comments + a review) ════════"
hg get decl:Gauss.isEven_mul_succ
#   re-derived body + lean_status, the preserved comments/review, formalizes/related_to.

echo; echo "════════ get the theorem (status, tags, origin, review, provenance) ════════"
hg get label:thm:gauss

echo; echo "════════ get the Mathlib-backed lemma (lean_status=mathlib_ok + name) ════════"
hg get label:lem:sum-succ

echo; echo "════════ ancestors of the theorem (what it depends on) ════════"
hg ancestors label:thm:gauss --names

echo; echo "════════ union view (blueprint ↔ Lean merged by 'formalizes') ════════"
hg view union

echo; echo "── 4. the site — one command, project view included, even solo ──"
# Everything generated goes under _site/ (gitignored): the example dir itself
# holds only sources. The workspace build at the repo root (`hgraph site`, see
# ../../config.yaml) renders this project too and is what GitHub Pages deploys —
# this solo page is just the "a lone project needs no manifest" demo.
hg site --out _site/index.html

echo; echo "view it:"
echo "  open directly:   xdg-open $HERE/_site/index.html"
echo "  or serve a dir:  (cd $HERE/_site && python -m http.server 8000)  → http://localhost:8000/"
echo "  the whole workspace: (cd $(cd "$HERE/../.." && pwd) && hgraph serve)"
