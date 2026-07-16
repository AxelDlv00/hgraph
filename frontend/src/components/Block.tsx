import { memo } from 'react';
import type { Block as BlockT, RefEntry } from '../types';
import type { CiteNums } from '../latex';
import { Math as Tex } from './Tex';
import { StmtBox } from './StmtBox';

/** Memoised: every prop except `selected` is stable per data fetch, so a
 * selection change (or a hydration step appending more blocks) re-renders
 * only the block(s) whose `selected` flipped instead of the whole chapter —
 * which matters because any re-render resets `dangerouslySetInnerHTML`
 * content and forces a KaTeX re-typeset (see Tex.tsx). */
export const BlockView = memo(function BlockView({
  b,
  refs,
  cites,
  macros,
  usedByCount,
  selected,
  onSelect,
  onNavigate,
  onCite,
}: {
  b: BlockT;
  refs: Record<string, RefEntry>;
  cites?: CiteNums;
  macros: Record<string, string>;
  usedByCount: number;
  selected: boolean;
  onSelect: (id: string) => void;
  onNavigate: (id: string) => void;
  onCite?: (key: string) => void;
}) {
  if (b.t === 'head') {
    const level = b.level > 4 ? 4 : b.level;
    const Tag = `h${level}` as 'h2' | 'h3' | 'h4';
    return (
      <Tag id={b.num ? `sec-${b.num}` : undefined}>
        {b.num && <span className="hn">{b.num}</span>}
        <Tex as="span" text={b.title} macros={macros} refs={refs} cites={cites} onNavigate={onNavigate} />
      </Tag>
    );
  }
  if (b.t === 'prose')
    return <Tex as="p" className="prose" text={b.tex} macros={macros} refs={refs} cites={cites} onNavigate={onNavigate} onCite={onCite} />;
  if (b.t === 'stmt')
    return (
      <StmtBox
        b={b}
        refs={refs}
        cites={cites}
        macros={macros}
        usedByCount={usedByCount}
        selected={selected}
        onSelect={onSelect}
        onNavigate={onNavigate}
        onCite={onCite}
      />
    );
  if (b.t === 'proof')
    return (
      <details className="proof">
        <summary>Proof</summary>
        <Tex as="div" className="pbody" text={b.tex} macros={macros} refs={refs} cites={cites} onNavigate={onNavigate} onCite={onCite} />
      </details>
    );
  return null;
});
