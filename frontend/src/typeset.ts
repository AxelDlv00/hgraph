// Lazily-loaded KaTeX auto-render, shared by every component that typesets
// math (Tex, HoverPreview, Bibliography, Landing's overview). KaTeX is the
// single biggest piece of the entry bundle, and the landing page usually has
// no math at all — splitting it out (see katexLoader.ts) means the first
// paint of every page ships without it; the chunk is fetched once, the first
// time any math actually needs typesetting, and prose is already readable
// (as raw `$…$`) for the instant before it lands.
let loader: Promise<(el: HTMLElement, opts: object) => void> | null = null;

function getRenderer() {
  if (!loader) loader = import('./katexLoader').then((m) => m.default);
  return loader;
}

const DELIMITERS = [
  { left: '\\[', right: '\\]', display: true },
  { left: '\\(', right: '\\)', display: false },
  { left: '$$', right: '$$', display: true },
  { left: '$', right: '$', display: false },
];

// What each element's first child was right after its last typeset. React 19
// re-sets `dangerouslySetInnerHTML` children on ANY re-render of the element
// — even when `__html` is the identical string — silently reverting KaTeX's
// output to raw `$…$`. Callers therefore run typesetMath after *every*
// commit (no dependency arrays); this map makes that O(1) when the children
// were left alone: a reset replaces all child nodes, so comparing the first
// child's identity tells the two cases apart without walking the tree.
const lastTypeset = new WeakMap<HTMLElement, Node | null>();

/** Typeset every math delimiter inside `el`, in place. Cheap to call after
 * every commit (see `lastTypeset`), safe to call twice (auto-render no-ops
 * once no literal `$…$` is left), and safe on malformed input
 * (`throwOnError: false`, plus a belt-and-braces catch). */
export function typesetMath(el: HTMLElement, macros?: Record<string, string>): void {
  if (lastTypeset.has(el) && lastTypeset.get(el) === el.firstChild) return;
  getRenderer().then((render) => {
    if (!el.isConnected) return; // unmounted while KaTeX was still loading
    try {
      render(el, {
        delimiters: DELIMITERS,
        macros: { '\\mbox': '\\text', '\\hbox': '\\text', ...macros },
        throwOnError: false,
      });
    } catch {
      // a malformed macro/expression shouldn't take the page down
    }
    lastTypeset.set(el, el.firstChild);
  });
}
