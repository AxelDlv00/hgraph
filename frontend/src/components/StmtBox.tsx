import type { StmtBlock, RefEntry, Dep } from '../types';
import type { CiteNums } from '../latex';
import { Math as Tex } from './Tex';
import { Reviews } from './Reviews';
import { Network } from 'lucide-react';

const ABBR: Record<string, string> = {
  definition: 'Def', lemma: 'Lem', theorem: 'Thm', proposition: 'Prop',
  corollary: 'Cor', remark: 'Rmk', example: 'Ex', conjecture: 'Conj',
};

/** The compact, document-flow statement box — tag/number, title, status
 * badge, prose body, and a row of small popup-trigger tags — ported from the
 * original `stmtBox()`. The statement's own body IS its full detail (this is
 * the document, not a compact graph node), so clicking the box just
 * navigates/highlights it in place; "uses/used-by" and "Lean" open a
 * click-pinned popup (wired globally in HoverPreview via the `data-graph`/
 * `data-lean` attributes below), never a side panel. */
export function StmtBox({
  b,
  refs,
  cites,
  macros,
  usedByCount,
  selected,
  onSelect,
  onNavigate,
  onOpenGraph,
  onCite,
  root,
  repo,
}: {
  b: StmtBlock;
  refs: Record<string, RefEntry>;
  cites?: CiteNums;
  macros: Record<string, string>;
  usedByCount: number;
  selected: boolean;
  onSelect: (id: string) => void;
  onNavigate: (id: string) => void;
  onOpenGraph: (id: string) => void;
  onCite?: (key: string) => void;
  /** review target + write path — the meta row offers a review inline, so a
   *  reader never has to open the graph to file one */
  root: string;
  repo: string | null;
}) {
  const en = b.enrich;
  const st = en ? en.lean_status : 'empty';
  const usesCount = (en?.deps || []).length;
  return (
    <div
      className={`stmt k-${b.content_type}${selected ? ' sel' : ''}`}
      id={`stmt-${b.id || ''}`}
      data-status={st}
    >
      <div className="sh">
        <span className="tag" onClick={() => b.id && onSelect(b.id)}>
          {b.abbr}&nbsp;{b.num}
        </span>
        {b.title && b.title !== b.label && <Tex as="span" className="st" text={b.title} refs={refs} />}
        <span className="badges">
          {en?.ref && (
            <span className="reftag" title="source reference">
              {en.ref}
            </span>
          )}
          {en?.sketch && (
            <span className="sketchtag" title="\sketch — the proof is deliberately a sketch">
              sketch
            </span>
          )}
          {en && <span className={`b b-${st}`}>{st.replace('_', ' ')}</span>}
        </span>
      </div>
      <Tex as="div" className="sbody" text={b.body} macros={macros} refs={refs} cites={cites} onNavigate={onNavigate} onCite={onCite} />
      {b.id && (
        <div className="smeta">
          <button
            type="button"
            className="mtag graph-open"
            onClick={() => onOpenGraph(b.id!)}
            title="Open this declaration in the dependency graph"
          >
            <Network size={13} strokeWidth={2} aria-hidden="true" />
            Open in graph
          </button>
          <span className="mtag pop" data-graph={b.id}>
            uses {usesCount} · used by {usedByCount}
          </span>
          {en?.lean && en.lean.length > 0 && (
            <span className="mtag pop lean" data-lean={b.id}>
              ✓ L∃∀N · {en.lean.length}
            </span>
          )}
          {!en?.lean?.length && en?.mathlib_name && (
            <span className="mtag pop mathlib" data-lean={b.id}>
              mathlib
            </span>
          )}
          {en && (
            <Reviews
              className="mtag rv"
              root={root}
              target={{ id: b.id, label: b.label || null, title: b.title || null }}
              reviews={en.reviews}
              comments={en.comments}
              repo={repo}
            />
          )}
        </div>
      )}
    </div>
  );
}

export function usedByIndex(entries: { id: string; deps: Dep[] }[]): Map<string, number> {
  const rev = new Map<string, number>();
  for (const e of entries) for (const d of e.deps) rev.set(d.id, (rev.get(d.id) || 0) + 1);
  return rev;
}

export { ABBR };
