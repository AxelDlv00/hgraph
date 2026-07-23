import { useRef, useEffect } from 'react';
import { typesetMath } from '../typeset';

/** A configured content page — a landing or blueprint custom tab, or the
 *  landing overview. The HTML is authored by the site owner (markdown converted
 *  by `hgraph.site._md_to_html`, or `.html` used verbatim) and trusted the same
 *  way the overview and footer already are; it is injected as-is and then KaTeX-
 *  typeset so `$…$` math renders. Extracted from Landing's former inner
 *  `Overview` so the landing page and ProjectView share one renderer.
 *
 *  No dependency array (same React-19 innerHTML-reset caveat as Tex.tsx);
 *  `typesetMath`'s guard makes the per-commit call O(1) when nothing changed. */
export function ContentPage({ html, className = 'overview' }: { html: string; className?: string }) {
  const ref = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (ref.current) typesetMath(ref.current);
  });
  return <section className={className} ref={ref as never} dangerouslySetInnerHTML={{ __html: html }} />;
}
