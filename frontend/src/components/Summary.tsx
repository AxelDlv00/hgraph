import { useMemo, useState } from 'react';
import type { Entry, Chapter, RefEntry, LeanDecl } from '../types';
import { Math as Tex } from './Tex';
import { ABBR } from './StmtBox';
import { statusColor } from '../palette';

/** A compact "statement card" for the summary lists — the original's
 * `sumBox`/`readyItem`: tag+number, title, status badge, and a row of
 * extra meta (stage/uses/unlocks or the sorry declaration). */
function SumBox({ e, status, meta, refs, onSelect }: {
  e: Entry;
  status: string;
  meta?: string;
  refs: Record<string, RefEntry>;
  onSelect: (id: string) => void;
}) {
  const r = (e.label && refs[e.label]) || null;
  return (
    <div className="stmt sum" data-status={status} onClick={() => onSelect(e.id)}>
      <div className="sh">
        <span className={`tag k-${e.kind}`}>
          {r?.abbr || ABBR[e.kind] || e.kind}
          {r?.num ? <>&nbsp;{r.num}</> : null}
        </span>
        <Tex as="span" className="st" text={e.title || e.label || e.id} refs={refs} />
        <span className="badges">
          <span className={`b b-${status}`}>{status.replace('_', ' ')}</span>
        </span>
      </div>
      {meta && <div className="rmeta" dangerouslySetInnerHTML={{ __html: meta }} />}
    </div>
  );
}

function segbar(cc: Record<string, number>, total: number) {
  const seg = (k: string) => (cc[k] ? <i key={k} style={{ width: `${(100 * cc[k]) / total}%`, background: statusColor(k) }} /> : null);
  return (
    <div className="segbar" title={`mathlib ${cc.mathlib_ok || 0} · lean ${cc.lean_ok || 0} · sorry ${cc.sorry || 0} · none ${cc.empty || 0}`}>
      {['mathlib_ok', 'lean_ok', 'sorry', 'empty'].map(seg)}
    </div>
  );
}

function sorryDecl(lean: LeanDecl[]): string {
  const sorries = lean.filter((l) => l.status === 'sorry').map((l) => l.name);
  return (sorries.length ? sorries : lean.map((l) => l.name)).join(', ');
}

const DONE = new Set(['lean_ok', 'mathlib_ok']);

interface SummaryData {
  total: number;
  completed: number;
  sorries: Entry[];
  noProof: number;
  depsInc: number;
  ready: { e: Entry; uses: number; unlocks: number }[];
}

/** Fully client-side closure analysis over the *documented* statement set —
 * mirrors the original's `computeSummary()` exactly, including its
 * (deliberate) treatment of a dependency that points outside the documented
 * set as "not closed". Kept self-contained (not the server's whole-graph
 * `Analysis`, which also counts undocumented Lean-only nodes) so every
 * number on this tab stays consistent with "Total entries". */
function computeSummary(entries: Entry[]): SummaryData {
  const byId = new Map(entries.map((e) => [e.id, e]));
  const F = (e?: Entry) => !!e && DONE.has(e.lean_status);
  const cm = new Map<string, boolean>();
  const inStack = new Set<string>();
  function closed(e?: Entry): boolean {
    if (!e) return false;
    const id = e.id;
    if (cm.has(id)) return cm.get(id)!;
    if (inStack.has(id)) return F(e);
    inStack.add(id);
    let r = F(e);
    if (r) {
      for (const d of e.deps) {
        if (!closed(byId.get(d.id))) {
          r = false;
          break;
        }
      }
    }
    inStack.delete(id);
    cm.set(id, r);
    return r;
  }
  entries.forEach((e) => closed(e));

  const rev = new Map<string, string[]>();
  for (const e of entries) for (const d of e.deps) (rev.get(d.id) || rev.set(d.id, []).get(d.id)!).push(e.id);
  const unlocksCache = new Map<string, number>();
  function unlocks(id: string): number {
    if (unlocksCache.has(id)) return unlocksCache.get(id)!;
    const seen = new Set<string>();
    const stack = [...(rev.get(id) || [])];
    while (stack.length) {
      const x = stack.pop()!;
      if (seen.has(x)) continue;
      seen.add(x);
      (rev.get(x) || []).forEach((y) => { if (!seen.has(y)) stack.push(y); });
    }
    unlocksCache.set(id, seen.size);
    return seen.size;
  }

  const sorries = entries.filter((e) => e.lean_status === 'sorry');
  const noProof = entries.filter((e) => e.lean_status === 'empty').length;
  const completed = entries.filter((e) => closed(e)).length;
  const depsInc = entries.filter((e) => F(e) && !closed(e)).length;
  const ready = entries
    .filter((e) => !F(e) && e.deps.every((d) => F(byId.get(d.id))))
    .map((e) => ({ e, uses: e.deps.length, unlocks: unlocks(e.id) }))
    .sort((a, b) => b.unlocks - a.unlocks);

  return { total: entries.length, completed, sorries, noProof, depsInc, ready };
}

/** The "Blueprint summary" tab — ready-now/blockers action lists plus a
 * per-chapter coverage table, ported from the original's
 * `computeSummary`/`renderSummary`. */
export function Summary({
  entries,
  chapters,
  refs,
  onSelect,
  onGotoChapter,
}: {
  entries: Entry[];
  chapters: Chapter[];
  refs: Record<string, RefEntry>;
  onSelect: (id: string) => void;
  onGotoChapter: (i: number) => void;
}) {
  const [readyAll, setReadyAll] = useState(false);
  const s = useMemo(() => computeSummary(entries), [entries]);
  const actionable = s.ready.filter((r) => r.unlocks > 0).length;

  const cards = [
    {
      v: s.total,
      l: 'Total entries',
      s: `completed ${s.completed} · deps incomplete ${s.depsInc} · sorries ${s.sorries.length} · no proof ${s.noProof}`,
    },
    { v: s.ready.length, l: 'Ready now', s: 'entries whose next formalization step is unblocked' },
    { v: s.completed, l: 'Fully closed', s: 'local code and prerequisite closure both complete' },
    { v: actionable, l: 'Actionable priorities', s: 'ready now and already unlocking downstream work' },
    { v: s.sorries.length, l: 'Current blockers', s: 'declarations with a sorry / incomplete Lean' },
  ];

  const readyShown = readyAll ? s.ready : s.ready.slice(0, 12);

  const chRows = chapters
    .map((ch, i) => {
      const stmts = ch.blocks.filter((b) => b.t === 'stmt');
      if (!stmts.length) return null;
      const cc: Record<string, number> = { mathlib_ok: 0, lean_ok: 0, sorry: 0, empty: 0 };
      stmts.forEach((b) => {
        const st = (b.t === 'stmt' && b.enrich?.lean_status) || 'empty';
        cc[st] = (cc[st] || 0) + 1;
      });
      const pct = Math.round((100 * (cc.lean_ok + cc.mathlib_ok)) / stmts.length);
      return { i, ch, count: stmts.length, cc, pct };
    })
    .filter((r): r is NonNullable<typeof r> => r !== null);

  return (
    <div className="doc">
      <h2 className="ch">Blueprint summary</h2>
      <div className="sumgrid">
        {cards.map((c) => (
          <div className="sumcard" key={c.l}>
            <div className="v">{c.v}</div>
            <div className="l">{c.l}</div>
            <div className="s">{c.s}</div>
          </div>
        ))}
      </div>

      <div className="sumsec">Ready next ({s.ready.length})</div>
      {s.ready.length === 0 && <div className="ro">Nothing is unblocked right now.</div>}
      {readyShown.map((r) => {
        const stage = r.e.lean_status === 'sorry' ? 'proof' : 'statement';
        const meta = `<span class="p">stage: <b>${stage}</b></span><span class="p">direct uses <b>${r.uses}</b></span><span class="p">downstream unlocks <b>${r.unlocks}</b></span>${r.e.lean.length ? `<span class="p">Lean: <b>${r.e.lean.length}</b></span>` : ''}`;
        return <SumBox key={r.e.id} e={r.e} status={r.e.lean_status} meta={meta} refs={refs} onSelect={onSelect} />;
      })}
      {s.ready.length > 12 && (
        <div className="morebtn" onClick={() => setReadyAll((v) => !v)}>
          {readyAll ? 'Show fewer' : `Show all ${s.ready.length} ready entries`}
        </div>
      )}

      <div className="sumsec">Current blockers ({s.sorries.length})</div>
      {s.sorries.length === 0 && <div className="ro">No sorries — nothing blocked.</div>}
      {s.sorries.slice(0, 40).map((e) => {
        const decl = sorryDecl(e.lean);
        const meta = decl ? `<span class="p">sorry in <b>${decl.replace(/</g, '&lt;')}</b></span>` : '';
        return <SumBox key={e.id} e={e} status="sorry" meta={meta} refs={refs} onSelect={onSelect} />;
      })}

      {chapters.length > 0 && (
        <>
          <div className="sumsec">Structure &amp; coverage</div>
          <table className="sumtable">
            <thead>
              <tr>
                <th>Chapter</th>
                <th>#</th>
                <th>progress</th>
              </tr>
            </thead>
            <tbody>
              {chRows.map((r) => (
                <tr key={r.i}>
                  <td>
                    <a onClick={() => onGotoChapter(r.i)}>
                      {r.ch.num} <Tex as="span" text={r.ch.title} refs={refs} />
                    </a>
                  </td>
                  <td>{r.count}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 9, alignItems: 'center' }}>
                      {segbar(r.cc, r.count)}
                      <span style={{ color: 'var(--muted)' }}>{r.pct}%</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
