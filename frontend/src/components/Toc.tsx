import { useState } from 'react';
import type { Chapter, RefEntry } from '../types';
import { chapterTree } from '../chapterTree';
import { plainTex } from '../latex';
import { Math as Tex } from './Tex';

function chapterStmtCount(ch: Chapter): number {
  return ch.blocks.filter((b) => b.t === 'stmt').length;
}

export type ViewName = 'overview' | 'doc' | 'summary' | 'biblio' | 'graph';

const NAV_LINKS: { view: ViewName; icon: string; label: string }[] = [
  { view: 'overview', icon: '▤', label: 'Overview' },
  { view: 'summary', icon: '▣', label: 'Blueprint summary' },
  { view: 'biblio', icon: '❞', label: 'Blueprint bibliography' },
  { view: 'graph', icon: '◆', label: 'Dependency graph' },
];

export function Toc({
  chapters,
  refs,
  curCh,
  onGoto,
  onGotoSection,
  query,
  onQuery,
  statusFilter,
  onToggleStatus,
  view,
  graphOpen,
  onSetView,
}: {
  chapters: Chapter[];
  refs: Record<string, RefEntry>;
  curCh: number;
  onGoto: (i: number) => void;
  onGotoSection: (i: number, num: string) => void;
  query: string;
  onQuery: (q: string) => void;
  statusFilter: Set<string>;
  onToggleStatus: (s: string) => void;
  view: ViewName;
  graphOpen: boolean;
  onSetView: (v: ViewName) => void;
}) {
  const [openCh, setOpenCh] = useState<Set<number>>(new Set());

  const toggleCh = (i: number) => {
    const next = new Set(openCh);
    next.has(i) ? next.delete(i) : next.add(i);
    setOpenCh(next);
  };

  return (
    <nav className="doc-nav">
      <input
        className="navq"
        placeholder="Search statements…"
        value={query}
        onChange={(e) => onQuery(e.target.value)}
      />
      <div className="navchips">
        {(['mathlib_ok', 'lean_ok', 'sorry', 'empty'] as const).map((s) => (
          <span
            key={s}
            className={`navchip${statusFilter.has(s) ? ' on' : ''}`}
            onClick={() => onToggleStatus(s)}
          >
            {s.replace('_', ' ')}
          </span>
        ))}
      </div>
      <div className="navlinks">
        {NAV_LINKS.map((n) => (
          <a
            key={n.view}
            className={`navlink${(n.view === 'graph' ? graphOpen : view === n.view) ? ' on' : ''}`}
            onClick={() => onSetView(n.view)}
          >
            <span className="ni">{n.icon}</span>
            {n.label}
          </a>
        ))}
      </div>
      {chapters.length > 0 && <div className="navsec">Chapters</div>}
      {chapters.map((ch, i) => {
        const open = openCh.has(i);
        return (
          <div key={i}>
            <div className={`tch${i === curCh ? ' sel' : ''}`} onClick={() => onGoto(i)}>
              <span className="tchev" onClick={(e) => { e.stopPropagation(); toggleCh(i); }}>
                {open ? '▾' : '▸'}
              </span>
              <span className="n">{ch.num}</span>
              <Tex as="span" text={ch.title} refs={refs} />
              <span className="c">{chapterStmtCount(ch)}</span>
            </div>
            {open &&
              chapterTree(ch)
                .filter((s) => s.num)
                .map((s) => (
                  <div key={s.num}>
                    <div className="tsec" onClick={() => onGotoSection(i, s.num)}>
                      <span className="tchev-sp" />
                      <span className="n">{s.num}</span>
                      <span>{plainTex(s.title)}</span>
                    </div>
                    {s.subs.map((u) => (
                      <div className="tsec l3" key={u.num} onClick={() => onGotoSection(i, u.num)}>
                        <span className="tchev-sp" />
                        <span className="n">{u.num}</span>
                        <span>{plainTex(u.title)}</span>
                      </div>
                    ))}
                  </div>
                ))}
          </div>
        );
      })}
    </nav>
  );
}
