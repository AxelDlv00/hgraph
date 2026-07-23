import { useState } from 'react';
import type { Chapter, ContentTab, RefEntry } from '../types';
import { chapterTree } from '../chapterTree';
import { plainTex } from '../latex';
import { Math as Tex } from './Tex';

function chapterStmtCount(ch: Chapter): number {
  return ch.blocks.filter((b) => b.t === 'stmt').length;
}

/** The built-in blueprint views. A project's own `site.tabs:` adds further
 *  content views whose ids are arbitrary strings, so `ViewName` stays open —
 *  the `(string & {})` keeps literal autocomplete for the built-ins while
 *  admitting any custom tab id. */
export type BuiltinView = 'overview' | 'doc' | 'summary' | 'biblio' | 'graph';
export type ViewName = BuiltinView | (string & {});

const NAV_LINKS: { view: BuiltinView; icon: string; label: string }[] = [
  { view: 'overview', icon: '▤', label: 'Overview' },
  { view: 'summary', icon: '▣', label: 'Blueprint summary' },
  { view: 'biblio', icon: '❞', label: 'Blueprint bibliography' },
  { view: 'graph', icon: '◆', label: 'Dependency graph' },
];

/** A custom tab's rail glyph: the config's `icon:` is used verbatim as a glyph/
 *  emoji (keeping the built-in text-glyph style), with a neutral default. */
const CUSTOM_TAB_ICON = '◈';

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
  customTabs = [],
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
  customTabs?: ContentTab[];
}) {
  const [openCh, setOpenCh] = useState<Set<number>>(new Set());

  const toggleCh = (i: number) => {
    const next = new Set(openCh);
    next.has(i) ? next.delete(i) : next.add(i);
    setOpenCh(next);
  };

  return (
    <nav className="doc-nav" id="blueprint-navigation" aria-label="Blueprint navigation">
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
        {customTabs.map((c) => (
          <a
            key={c.id}
            className={`navlink${view === c.id ? ' on' : ''}`}
            onClick={() => onSetView(c.id)}
          >
            <span className="ni">{c.icon || CUSTOM_TAB_ICON}</span>
            {c.label}
          </a>
        ))}
      </div>
      {chapters.length > 0 && <div className="navsec">Chapters</div>}
      {chapters.map((ch, i) => {
        const open = openCh.has(i);
        // \appendix: mark where the back matter starts rather than letting the
        // appendices read as more chapters
        const startsAppendix = !!ch.appendix && !chapters[i - 1]?.appendix;
        return (
          <div key={i}>
            {startsAppendix && <div className="navsec">Appendices</div>}
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
