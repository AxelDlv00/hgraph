import type { Entry, Dep, RefEntry } from '../types';
import { leanHi, type CiteNums } from '../latex';
import { Math as Tex } from './Tex';
import { StatusBadge } from './StatusBadge';
import { Reviews } from './Reviews';
import { localDepGraph } from '../depgraph';

const ABBR: Record<string, string> = {
  definition: 'Def', lemma: 'Lem', theorem: 'Thm', proposition: 'Prop',
  corollary: 'Cor', remark: 'Rmk', example: 'Ex', conjecture: 'Conj',
  proof: 'Proof', quote: 'Quote', instance: 'Instance',
};

function DepList({
  deps,
  label,
  macros,
  onNavigate,
}: {
  deps: Dep[];
  label: string;
  macros: Record<string, string>;
  onNavigate?: (id: string) => void;
}) {
  if (!deps.length) return null;
  return (
    <div className="deps-row">
      <span className="deps-label">{label}</span>
      {deps.map((d) => (
        // no href — a real "#stmt-<id>" fragment would clobber the app's
        // "#/<root>#<locator>" hash route and 404 the whole SPA; chips select
        // within the current panel instead
        <a key={d.id} className="dep-chip" onClick={() => onNavigate?.(d.id)}>
          <Tex as="span" text={d.title || d.label || d.id} macros={macros} />
        </a>
      ))}
    </div>
  );
}

export function StatementCard({
  entry,
  usedBy,
  byId,
  root,
  repo,
  macros,
  refs,
  cites,
  onNavigate,
}: {
  entry: Entry;
  usedBy: Dep[];
  byId: Map<string, Entry>;
  root: string;
  repo: string | null;
  macros: Record<string, string>;
  /** without these, \ref renders as bare text and \cite as a raw bib key */
  refs?: Record<string, RefEntry>;
  cites?: CiteNums;
  /** clicking a \ref link in the body selects that statement */
  onNavigate?: (id: string) => void;
}) {
  const ups = entry.deps.map((d) => byId.get(d.id)).filter((x): x is Entry => !!x);
  const downs = usedBy.map((d) => byId.get(d.id)).filter((x): x is Entry => !!x);

  return (
    <div className="stmt-card" id={`stmt-${entry.id}`}>
      <div className="stmt-head">
        <span className="stmt-kind">{ABBR[entry.kind] || entry.kind}</span>
        <Tex as="span" className="stmt-title" text={entry.title || entry.label || entry.id} macros={macros} refs={refs} cites={cites} />
        <span className="stmt-badges">
          <StatusBadge status={entry.lean_status} />
        </span>
      </div>

      {entry.body && <Tex as="p" className="stmt-body" text={entry.body} macros={macros} refs={refs} cites={cites} onNavigate={onNavigate} />}

      {entry.mathlib_name && entry.mathlib_name.length > 0 && (
        <div className="stmt-mathlib">
          Mathlib: <code>{entry.mathlib_name.join(', ')}</code>
        </div>
      )}

      {entry.lean.length > 0 && (
        <div className="stmt-lean">
          {entry.lean.map((l) => (
            <div key={l.name} className="lean-block">
              <div className="lean-head">
                <code>{l.name}</code>
                <StatusBadge status={l.status} />
              </div>
              {/* leanHi escapes the code before adding highlight spans */}
              {l.code && <pre className="lean-code" dangerouslySetInnerHTML={{ __html: leanHi(l.code) }} />}
            </div>
          ))}
        </div>
      )}

      <DepList deps={entry.deps} label="uses" macros={macros} onNavigate={onNavigate} />
      <DepList deps={usedBy} label="used by" macros={macros} onNavigate={onNavigate} />

      <h3>Dependencies</h3>
      <div dangerouslySetInnerHTML={{ __html: localDepGraph(entry, ups, downs, true) }} />

      <Reviews root={root} target={entry} reviews={entry.reviews} comments={entry.comments} repo={repo} />
    </div>
  );
}
