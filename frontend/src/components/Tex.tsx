import { useEffect, useMemo, useRef } from 'react';
import { proseHtml, type CiteNums, type RefEntry } from '../latex';
import { typesetMath } from '../typeset';

/**
 * Renders `text` as full text-mode LaTeX -> HTML (see latex.ts's `detex`):
 * `\emph{}`, lists, quotes, accents, `\ref`/`\cite` links, … — with math
 * spans left for KaTeX's auto-render (lazily loaded through typeset.ts, so
 * the entry bundle doesn't carry KaTeX; the old dashboard loaded the same
 * katex/contrib/auto-render from a CDN script tag).
 * `refs` resolves `\ref`/`\cref` to numbered links; `onNavigate`/`onCite`
 * handle clicks on those links (event-delegated, since the content is raw
 * HTML, not JSX).
 */
export function Math({
  text,
  macros,
  refs,
  cites,
  as: As = 'span',
  className,
  onNavigate,
  onCite,
}: {
  text?: string | null;
  macros?: Record<string, string>;
  refs?: Record<string, RefEntry>;
  /** bib key -> number, so `\cite` renders as "[2]" (see latex.ts's citeNums) */
  cites?: CiteNums;
  as?: 'span' | 'div' | 'p';
  className?: string;
  onNavigate?: (id: string) => void;
  onCite?: (key: string) => void;
}) {
  const ref = useRef<HTMLElement | null>(null);

  // Memoised so re-renders hand React the *same string*: React only rewrites
  // `dangerouslySetInnerHTML` when the `__html` value changes, so KaTeX's
  // in-place typesetting survives unrelated re-renders (a sibling selection
  // change, a filter keystroke) untouched — and the `detex` regex pipeline
  // runs once per content, not once per render.
  const html = useMemo(() => {
    const full = proseHtml(text, refs, cites);
    return As === 'p' ? full : full.replace(/^<p>/, '').replace(/<\/p>$/, '');
  }, [text, refs, cites, As]);

  // No dependency array: React 19 re-sets `dangerouslySetInnerHTML` children
  // on any re-render of this element — even with `__html` unchanged — which
  // reverts KaTeX output to raw `$…$`. typesetMath detects that reset in
  // O(1) (see typeset.ts) and only re-typesets when it really happened.
  useEffect(() => {
    if (ref.current) typesetMath(ref.current, macros);
  });

  return (
    <As
      ref={ref as never}
      className={className}
      dangerouslySetInnerHTML={{ __html: html }}
      onClick={(e: React.MouseEvent) => {
        const t = e.target as HTMLElement;
        const refEl = t.closest('.ref[data-id]') as HTMLElement | null;
        if (refEl && onNavigate) return onNavigate(refEl.dataset.id!);
        const citeEl = t.closest('.cite[data-cite]') as HTMLElement | null;
        if (citeEl && onCite) return onCite(citeEl.dataset.cite!);
      }}
    />
  );
}
