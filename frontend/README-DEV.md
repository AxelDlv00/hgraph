# hgraph frontend (dev)

The whole site (`hgraph site`) is one React/Vite app — a landing page and a
per-project view, hash-routed client-side (`#/`, `#/<root>`). There is no
separate "dashboard" artifact; one project or many, it's all this app. This
directory is the *source* — end users never touch it; `pip install hgraph`
ships the already-built output at `../hgraph/webui/`.

```bash
npm install
npm run dev      # local dev server with HMR (fetches /api/site, /<root>/data.json
                  # from nowhere useful on its own — point it at a running
                  # `hgraph serve` if you need real data)
npm run build    # writes straight into ../hgraph/webui/ (outDir in vite.config.ts)
```

**After any change here, run `npm run build` and commit the updated
`hgraph/webui/` output** — that's the artifact that actually ships.

Data contracts: `src/types.ts` — `SiteData` (landing, `window.__HGRAPH_DATA__`
or `GET /api/site`) and `ProjectData` (`<root>/data.json`, written by
`hgraph.dashboard.project_data`). Python only ever emits these two JSON
shapes; every bit of rendering — math (`katex/contrib/auto-render`), Lean
code, dependency chips, the review form — lives here.

Scope note: the project view (`ProjectView.tsx`) covers statements, Lean
code, dependencies, and reviews/comments. Deliberately not (yet) ported from
the old Python renderer: the interactive dependency-graph visualization,
hover-preview popups, a search/filter sidebar, and bibliography rendering.
