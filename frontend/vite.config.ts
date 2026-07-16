import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// KaTeX's CSS ships woff2 + woff + ttf fallbacks for every font, but woff2
// alone covers every browser this app targets — the fallbacks just triple
// the font payload for nothing. This bundle is shared and cached across the
// whole workspace (one copy for every project + the landing page), so
// trimming it is worth it. Same trick the old Python vendoring used to do
// server-side (`_vendor_katex`), just applied to the Vite build instead.
function trimFontFallbacks(): Plugin {
  return {
    name: 'trim-font-fallbacks',
    generateBundle(...args) {
      const bundle = args[1]
      const drop = new Set<string>()
      for (const file of Object.values(bundle)) {
        if (file.type !== 'asset' || !file.fileName.endsWith('.css')) continue
        if (typeof file.source !== 'string') continue
        file.source = file.source.replace(
          /,url\((\.\/[^)]+\.(?:woff|ttf))\)format\("(?:woff|truetype)"\)/g,
          (_m, rel: string) => { drop.add(rel.replace(/^\.\//, '')); return '' },
        )
      }
      for (const name of drop) {
        const key = Object.keys(bundle).find((k) => k.endsWith(name))
        if (key) delete bundle[key]
      }
    },
  }
}

// base: './' — the built assets are referenced with relative paths, so the
// same build works whether it's opened at the repo root, one level under a
// workspace landing page, live via `hgraph serve`, or on GitHub Pages.
//
// outDir points *inside the Python package* (../hgraph/webui) — this is a
// pre-built bundle shipped with hgraph, per pyproject.toml's package-data.
// `npm run build` here is a dev-time step for whoever edits the frontend;
// end users of `pip install hgraph` never need Node.
export default defineConfig({
  plugins: [react(), trimFontFallbacks()],
  base: './',
  build: {
    outDir: '../hgraph/webui',
    emptyOutDir: true,
  },
})
