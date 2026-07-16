# About this example

A small worked graph: [Gauss's summation
formula](https://en.wikipedia.org/wiki/1_%2B_2_%2B_3_%2B_4_%2B_%E2%8B%AF),
synced from a `leanblueprint`-style `.tex` and matching Lean sources, then
layered with provenance, tags, comments, and reviews by hand.

- `hgraph sync` parses the blueprint + Lean into nodes and edges.
- A human/agent adds what the sources can't hold: `origin`, `status`, `tags`, failure-memory `comment`s, and Maths/Lean `review`s.
- Re-running `sync` is idempotent — none of the above is ever clobbered.

See the [source and build script](https://github.com/AxelDlv00/hgraph/tree/main/examples/gauss).
