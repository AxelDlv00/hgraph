import type { StmtBlock, RefEntry, Dep } from '../types';
import { leanHi, type CiteNums } from '../latex';
import { Math as Tex } from './Tex';
import { Reviews } from './Reviews';
import { Network } from 'lucide-react';

const ABBR: Record<string, string> = {
  definition: 'Def', lemma: 'Lem', theorem: 'Thm', proposition: 'Prop',
  corollary: 'Cor', remark: 'Rmk', example: 'Ex', conjecture: 'Conj',
};

/** The compact, document-flow statement box — tag/number, title, status
 * badge, prose body, and expandable metadata sections. The statement's own
 * body IS its full detail (this is the document, not a compact graph node), so
 * clicking the box just navigates/highlights it in place. */

function DependencyDetails({
  uses,
  usedBy,
  refs,
  macros,
  onNavigate,
}: {
  uses: Dep[];
  usedBy: Dep[];
  refs: Record<string, RefEntry>;
  macros: Record<string, string>;
  onNavigate: (id: string) => void;
}) {
  const links = (items: Dep[], empty: string) =>
    items.length ? (
      <div className="stmt-detail-links">
        {items.map((d) => (
          <button key={d.id} type="button" className="stmt-detail-link" onClick={() => onNavigate(d.id)}>
            <Tex as="span" text={d.title || d.label || d.id} macros={macros} refs={refs} />
          </button>
        ))}
      </div>
    ) : (
      <div className="stmt-detail-empty">{empty}</div>
    );

  return (
    <details className="stmt-detail">
      <summary className="mtag mtag-detail-summary">uses {uses.length} · used by {usedBy.length}</summary>
      <div className="stmt-detail-body stmt-deps-body">
        <section>
          <div className="stmt-detail-label">Uses</div>
          {links(uses, 'No direct dependencies.')}
        </section>
        <section>
          <div className="stmt-detail-label">Used by</div>
          {links(usedBy, 'Nothing depends on this yet.')}
        </section>
      </div>
    </details>
  );
}

function LeanDetails({
  lean,
  mathlibName,
}: {
  lean: NonNullable<StmtBlock['enrich']>['lean'];
  mathlibName: string[] | null;
}) {
  if (!lean.length && !mathlibName) return null;
  if (!lean.length) {
    return (
      <details className="stmt-detail">
        <summary className="mtag mathlib mtag-detail-summary">mathlib</summary>
        <div className="stmt-detail-body stmt-mathlib-body"><code>{mathlibName!.join(', ')}</code></div>
      </details>
    );
  }
  return (
    <details className="stmt-detail">
      <summary className="mtag lean mtag-detail-summary">✓ L∃∀N · {lean.length}</summary>
      <div className="stmt-detail-body stmt-lean-body">
        {lean.map((l) => (
          <div key={l.name} className="lean-block">
            <div className="lean-head">
              <code>{l.name}</code>
              <span className={`b b-${l.status || 'empty'}`}>{(l.status || 'empty').replace('_', ' ')}</span>
            </div>
            {l.code && <pre className="lean-code" dangerouslySetInnerHTML={{ __html: leanHi(l.code) }} />}
          </div>
        ))}
      </div>
    </details>
  );
}

export function StmtBox({
  b,
  refs,
  cites,
  macros,
  usedBy,
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
  usedBy: Dep[];
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
  const uses = en?.deps || [];
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
          <DependencyDetails uses={uses} usedBy={usedBy} refs={refs} macros={macros} onNavigate={onNavigate} />
          {en && <LeanDetails lean={en.lean} mathlibName={en.mathlib_name} />}
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
