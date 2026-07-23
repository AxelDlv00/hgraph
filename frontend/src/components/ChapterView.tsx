import { useEffect, useLayoutEffect, useState } from 'react';
import type { Block as BlockT, Chapter, RefEntry, StmtBlock } from '../types';
import { BlockView } from './Block';
import { Math as Tex } from './Tex';
import { plainTex } from '../latex';
import type { CiteNums } from '../latex';
import { chapterTree } from '../chapterTree';
import { ChapterContentsTree } from './ChapterContents';

function ChapterOverview({
  ch,
  refs,
  onGoto,
  onGotoSection,
}: {
  ch: Chapter;
  refs: Record<string, RefEntry>;
  onGoto: (id: string) => void;
  onGotoSection: (num: string) => void;
}) {
  const stmts = ch.blocks.filter((b): b is StmtBlock => b.t === 'stmt');
  const sections = chapterTree(ch);
  if (!stmts.length && !sections.length) return null;
  const cc: Record<string, number> = { mathlib_ok: 0, lean_ok: 0, sorry: 0, empty: 0 };
  stmts.forEach((b) => {
    const s = b.enrich ? b.enrich.lean_status : 'empty';
    cc[s] = (cc[s] || 0) + 1;
  });
  const pct = stmts.length ? Math.round((100 * (cc.lean_ok + cc.mathlib_ok)) / stmts.length) : 0;
  return (
    <details className="choverview" open>
      <summary>
        Chapter contents · <b>{stmts.length}</b> statements · <b>{pct}%</b> formalized
      </summary>
      <ChapterContentsTree
        sections={sections}
        refs={refs}
        onGotoStatement={onGoto}
        onGotoSection={onGotoSection}
      />
    </details>
  );
}

/** The anchor id a block answers to (deep links, \ref clicks, TOC jumps, and
 * a bibliography "Cited in" jump). Statements and numbered headings keep their
 * semantic ids; every other block gets a positional `blk-<index>` so a prose
 * or proof citation is addressable too (unique within the mounted chapter —
 * only one chapter is in the DOM at a time). */
function blockAnchor(b: BlockT, i: number): string {
  if (b.t === 'stmt' && b.id) return `stmt-${b.id}`;
  if (b.t === 'head' && b.num) return `sec-${b.num}`;
  return `blk-${i}`;
}

/** An `eq-<num>` anchor belongs to a display equation *inside* a block, marked
 * by the `\tag{<num>}` the backend wrote into its TeX — so a `\cref{eq:…}`
 * still knows which block to hydrate before scrolling. */
function holdsAnchor(b: BlockT, i: number, anchor: string): boolean {
  if (blockAnchor(b, i) === anchor) return true;
  if (!anchor.startsWith('eq-')) return false;
  const tex = b.t === 'stmt' ? b.body : b.t === 'prose' || b.t === 'proof' ? b.tex : '';
  return tex.includes(`\\tag{${anchor.slice(3)}}`);
}

/** A not-yet-hydrated block: keeps the block's anchor id and roughly its
 * shape so the scrollbar doesn't jump wildly, at none of the LaTeX/KaTeX
 * cost. Headings render their (plain-text) title immediately — they're cheap
 * and keep the chapter scannable while statements stream in. */
function BlockPlaceholder({ b }: { b: BlockT }) {
  if (b.t === 'head') {
    const level = b.level > 4 ? 4 : b.level;
    const Tag = `h${level}` as 'h2' | 'h3' | 'h4';
    return (
      <Tag id={b.num ? `sec-${b.num}` : undefined}>
        {b.num && <span className="hn">{b.num}</span>}
        {plainTex(b.title)}
      </Tag>
    );
  }
  if (b.t === 'stmt') return <div className="stmt blk-pending" id={`stmt-${b.id || ''}`} />;
  return <div className="blk-pending blk-pending-prose" />;
}

// First paint mounts this many blocks; the rest hydrate in idle-time chunks.
// Small enough that switching to any chapter paints instantly, large enough
// that a typical viewport is fully real content from the first frame.
const INITIAL_BLOCKS = 16;
const HYDRATE_CHUNK = 14;

export function ChapterView({
  chapter,
  refs,
  cites,
  macros,
  usedBy,
  selectedId,
  onSelect,
  onNavigate,
  onGotoSection,
  onOpenGraph,
  onCite,
  anchor,
  root,
  repo,
}: {
  chapter: Chapter;
  refs: Record<string, RefEntry>;
  cites?: CiteNums;
  macros: Record<string, string>;
  usedBy: Map<string, number>;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNavigate: (id: string) => void;
  onGotoSection: (num: string) => void;
  onOpenGraph: (id: string) => void;
  onCite?: (key: string) => void;
  /** element id a pending scroll wants to land on (see ProjectView.navigate) */
  anchor?: string | null;
  /** passed through to each statement's review panel (see StmtBox) */
  root: string;
  repo: string | null;
}) {
  const blocks = chapter.blocks;
  const [mounted, setMounted] = useState(() => Math.min(INITIAL_BLOCKS, blocks.length));

  // A requested scroll target must be real — and so must everything ABOVE it,
  // or later hydration would shift it mid-read — before ProjectView's rAF
  // scroll fires. Mount through it synchronously; worst case (a target at the
  // chapter's end) that's the full chapter, which is exactly what every
  // render paid before hydration existed.
  useLayoutEffect(() => {
    if (!anchor) return;
    const idx = blocks.findIndex((b, i) => holdsAnchor(b, i, anchor));
    if (idx >= 0) setMounted((m) => Math.max(m, idx + 1));
  }, [anchor, blocks]);

  // hydrate the rest progressively, one idle-time chunk after another
  useEffect(() => {
    if (mounted >= blocks.length) return;
    let alive = true;
    const step = () => {
      if (alive) setMounted((m) => Math.min(m + HYDRATE_CHUNK, blocks.length));
    };
    const handle =
      typeof requestIdleCallback === 'function'
        ? requestIdleCallback(step, { timeout: 400 })
        : window.setTimeout(step, 40);
    return () => {
      alive = false;
      if (typeof cancelIdleCallback === 'function') cancelIdleCallback(handle as number);
      else window.clearTimeout(handle as number);
    };
  }, [mounted, blocks.length]);

  return (
    <div className="doc">
      <h2 className="ch">
        {chapter.num && <span className="hn">{chapter.num}</span>}
        <Tex as="span" text={chapter.title} refs={refs} />
      </h2>
      <ChapterOverview
        ch={chapter}
        refs={refs}
        onGoto={onNavigate}
        onGotoSection={onGotoSection}
      />
      {blocks.slice(0, mounted).map((b, i) => (
        <BlockView
          key={i}
          b={b}
          anchorId={blockAnchor(b, i)}
          refs={refs}
          cites={cites}
          macros={macros}
          usedByCount={(b.t === 'stmt' && b.id && usedBy.get(b.id)) || 0}
          selected={b.t === 'stmt' && !!b.id && b.id === selectedId}
          onSelect={onSelect}
          onNavigate={onNavigate}
          onOpenGraph={onOpenGraph}
          onCite={onCite}
          root={root}
          repo={repo}
        />
      ))}
      {blocks.slice(mounted).map((b, j) => (
        <BlockPlaceholder key={mounted + j} b={b} />
      ))}
    </div>
  );
}
