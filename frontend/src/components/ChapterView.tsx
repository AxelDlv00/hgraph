import { useEffect, useLayoutEffect, useState } from 'react';
import type { Block as BlockT, Chapter, RefEntry, StmtBlock } from '../types';
import { BlockView } from './Block';
import { Math as Tex } from './Tex';
import { statusColor } from '../palette';
import { plainTex } from '../latex';
import type { CiteNums } from '../latex';

interface Section {
  num: string;
  title: string;
  stmts: StmtBlock[];
}

function chapterSections(ch: Chapter): Section[] {
  const rows: Section[] = [];
  let cur: Section | null = null;
  for (const b of ch.blocks) {
    if (b.t === 'head' && b.level >= 2 && b.level <= 3 && b.num) {
      cur = { num: b.num, title: b.title, stmts: [] };
      rows.push(cur);
    } else if (b.t === 'stmt') {
      if (!cur) {
        cur = { num: '', title: '', stmts: [] };
        rows.push(cur);
      }
      cur.stmts.push(b);
    }
  }
  return rows;
}

function ChapterOverview({ ch, refs, onGoto }: { ch: Chapter; refs: Record<string, RefEntry>; onGoto: (id: string) => void }) {
  const stmts = ch.blocks.filter((b): b is StmtBlock => b.t === 'stmt');
  const rows = chapterSections(ch);
  if (!stmts.length && !rows.length) return null;
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
      {rows.map((r, i) => (
        <div className="co-row" key={i}>
          {r.num ? (
            <div className="co-sec">
              <span className="n">{r.num}</span>
              <Tex as="span" text={r.title} refs={refs} />
            </div>
          ) : (
            <span className="co-sec" style={{ color: 'var(--muted)' }}>
              Introduction
            </span>
          )}
          <div className="co-rowmap">
            {r.stmts.map((b) => {
              const st = b.enrich ? b.enrich.lean_status : 'empty';
              return (
                <i
                  key={b.id}
                  className="mm"
                  style={{ background: statusColor(st) }}
                  onClick={() => b.id && onGoto(b.id)}
                />
              );
            })}
          </div>
        </div>
      ))}
    </details>
  );
}

/** The anchor id a block answers to (deep links, \ref clicks, TOC jumps). */
function blockAnchor(b: BlockT): string | null {
  if (b.t === 'stmt' && b.id) return `stmt-${b.id}`;
  if (b.t === 'head' && b.num) return `sec-${b.num}`;
  return null;
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
  onCite,
  anchor,
}: {
  chapter: Chapter;
  refs: Record<string, RefEntry>;
  cites?: CiteNums;
  macros: Record<string, string>;
  usedBy: Map<string, number>;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNavigate: (id: string) => void;
  onCite?: (key: string) => void;
  /** element id a pending scroll wants to land on (see ProjectView.navigate) */
  anchor?: string | null;
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
    const idx = blocks.findIndex((b) => blockAnchor(b) === anchor);
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
      <ChapterOverview ch={chapter} refs={refs} onGoto={onNavigate} />
      {blocks.slice(0, mounted).map((b, i) => (
        <BlockView
          key={i}
          b={b}
          refs={refs}
          cites={cites}
          macros={macros}
          usedByCount={(b.t === 'stmt' && b.id && usedBy.get(b.id)) || 0}
          selected={b.t === 'stmt' && !!b.id && b.id === selectedId}
          onSelect={onSelect}
          onNavigate={onNavigate}
          onCite={onCite}
        />
      ))}
      {blocks.slice(mounted).map((b, j) => (
        <BlockPlaceholder key={mounted + j} b={b} />
      ))}
    </div>
  );
}
