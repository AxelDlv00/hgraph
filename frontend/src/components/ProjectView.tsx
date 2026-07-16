import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ProjectData, Dep, StmtBlock } from '../types';
import { ChapterView } from './ChapterView';
import { Toc, type ViewName } from './Toc';
import { Outline } from './Outline';
import { Overview } from './Overview';
import { StmtBox } from './StmtBox';
import { HoverPreview } from './HoverPreview';
import { GraphModal } from './GraphModal';
import { Summary } from './Summary';
import { Bibliography } from './Bibliography';
import { citeNums, plainTex } from '../latex';

// how many search results render at once — past this, a broad query (one
// letter, or a bare status chip on a large blueprint) would typeset hundreds
// of KaTeX boxes for content nobody scrolls through
const MAX_RESULTS = 120;

function flashEl(id: string) {
  requestAnimationFrame(() => {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.add('flash');
    window.setTimeout(() => el.classList.remove('flash'), 1700);
  });
}

export function ProjectView({ root, initialLocator }: { root: string; initialLocator?: string | null }) {
  const [data, setData] = useState<ProjectData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [curCh, setCurCh] = useState(0);
  // `selectedId` is doc-view highlighting only (no panel — the statement's
  // body IS already its own detail, right there in the document). The graph
  // tab is a separate, compact node view that genuinely needs a detail side
  // panel when you click a node — that's `graphSelectedId`, kept apart so
  // switching tabs never leaks one view's selection into the other's panel.
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // the dependency graph is a full-screen modal (`GraphModal`), not a main-
  // content tab — `graphOpen` tracks it independently of `view`, and
  // `graphSelectedId` is its own node-detail-panel selection, matching the
  // original's separate `GM.open`/`GM.sel`.
  const [graphOpen, setGraphOpen] = useState(false);
  const [graphSelectedId, setGraphSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set());
  // the element id a just-requested navigation wants to scroll to — ChapterView
  // hydrates its blocks progressively and force-mounts through this anchor so
  // the scroll target (and everything above it) is real before the scroll fires
  const [anchor, setAnchor] = useState<string | null>(null);
  // "overview" (the title page + drill-down squares) is the default landing
  // view for a multi-chapter blueprint, same as the original's boot-time
  // `renderOverview()` — a specific chapter's full prose ("doc") is one
  // click away, not the default.
  const [view, setView] = useState<ViewName>('overview');

  useEffect(() => {
    setData(null);
    setError(null);
    fetch(`${root}/data.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [root]);

  // keep the URL's "#/<root>#<locator>" in sync with the current statement/
  // chapter, so external links (e.g. a proof-structure diagram) can deep-link
  // back in — mirrors the original page-level dashboard's `setHash`/`gotoHash`.
  // `hashnav` guards our own `replaceState` calls from being mistaken for a
  // user-driven navigation on the next hashchange.
  const hashnav = useRef(false);
  const setHash = useCallback((frag: string) => {
    hashnav.current = true;
    try {
      history.replaceState(null, '', `#/${root}#${encodeURIComponent(frag)}`);
    } catch {
      // ignore — deep-link sync is a nicety, not load-bearing
    }
    requestAnimationFrame(() => { hashnav.current = false; });
  }, [root]);

  // reverse dependency index ("used by"), computed once per fetch
  const usedByMap = useMemo(() => {
    const map = new Map<string, Dep[]>();
    if (!data) return map;
    for (const e of data.entries) {
      for (const d of e.deps) {
        const back: Dep = { id: e.id, title: e.title, label: e.label, type: d.type };
        if (!map.has(d.id)) map.set(d.id, []);
        map.get(d.id)!.push(back);
      }
    }
    return map;
  }, [data]);
  const usedByCounts = useMemo(() => {
    const m = new Map<string, number>();
    usedByMap.forEach((v, k) => m.set(k, v.length));
    return m;
  }, [usedByMap]);
  const byId = useMemo(() => new Map((data?.entries || []).map((e) => [e.id, e])), [data]);

  // stable identities per fetch — BlockView is memoised on these
  const refs = useMemo(() => data?.refs || {}, [data]);
  const chapters = useMemo(() => data?.chapters || [], [data]);
  // \cite{key} renders as its bibliography number, the way LaTeX numbers it
  const cites = useMemo(() => citeNums(data?.bib), [data]);

  // useCallback: navigate is a prop of every memoised BlockView — a fresh
  // closure per render would defeat the memo and re-render whole chapters
  const navigate = useCallback((id: string) => {
    setView('doc');
    if (!chapters.length) {
      setSelectedId(id);
      return;
    }
    setQuery('');
    setStatusFilter(new Set());
    const loc = data?.loc?.[id];
    if (loc !== undefined && loc !== curCh) setCurCh(loc);
    setSelectedId(id);
    setAnchor(`stmt-${id}`);
    requestAnimationFrame(() => {
      document.getElementById(`stmt-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    flashEl(`stmt-${id}`);
    const e = data?.entries.find((x) => x.id === id);
    setHash(e?.label || id);
  }, [data, chapters, curCh, setHash]);

  function gotoSection(chapterIndex: number, num: string) {
    setView('doc');
    setCurCh(chapterIndex);
    setSelectedId(null);
    setAnchor(`sec-${num}`);
    requestAnimationFrame(() => {
      document.getElementById(`sec-${num}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  function gotoChapter(chapterIndex: number) {
    setView('doc');
    setQuery('');
    setStatusFilter(new Set());
    setCurCh(chapterIndex);
    setSelectedId(null);
    setAnchor(null);
    setHash(`ch-${chapterIndex + 1}`);
  }

  // honour an incoming "#/<root>#<locator>" once the data's loaded — same
  // syntax the original's `gotoHash` understood (a chapter "ch-N"/"chapter-N",
  // an optional "stmt-" prefix, or a raw \label / node id).
  useEffect(() => {
    if (!data || !initialLocator) return;
    let h = initialLocator;
    const chMatch = h.match(/^(?:ch|chapter)-(\d+)$/i);
    if (chMatch) {
      const i = Number(chMatch[1]) - 1;
      if (data.chapters?.[i]) gotoChapter(i);
      return;
    }
    if (h.startsWith('stmt-')) h = h.slice(5);
    const byLabel = data.entries.find((e) => e.label === h);
    const id = data.entries.some((e) => e.id === h) ? h : byLabel?.id;
    if (id) navigate(id);
  }, [data]);

  function toggleStatus(s: string) {
    setView('doc');
    const next = new Set(statusFilter);
    next.has(s) ? next.delete(s) : next.add(s);
    setStatusFilter(next);
  }

  function onQueryChange(q: string) {
    setView('doc');
    setQuery(q);
  }

  const [flashBibKey, setFlashBibKey] = useState<string | null>(null);
  const onCite = useCallback((key: string) => {
    setView('biblio');
    setFlashBibKey(key);
    requestAnimationFrame(() => {
      document.querySelector(`.bibitem[data-key="${CSS.escape(key)}"]`)?.scrollIntoView({ block: 'center' });
    });
    window.setTimeout(() => setFlashBibKey(null), 1700);
  }, []);

  // debounce the query so each keystroke doesn't rebuild + re-render the
  // whole results list; the input itself stays controlled by `query`
  const [debouncedQuery, setDebouncedQuery] = useState('');
  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQuery(query), 120);
    return () => window.clearTimeout(t);
  }, [query]);

  // searchable plain text per statement, built once per data fetch instead of
  // running plainTex over every body on every keystroke
  const searchText = useMemo(() => {
    const m = new Map<StmtBlock, string>();
    for (const ch of chapters)
      for (const b of ch.blocks)
        if (b.t === 'stmt') m.set(b, (plainTex(b.title) + ' ' + plainTex(b.body)).toLowerCase());
    return m;
  }, [chapters]);

  // search/filter across all statements — matches when a query and/or status
  // filter is active, ported from the original's "results mode"
  const filtered = useMemo(() => {
    if (!data || (!debouncedQuery.trim() && statusFilter.size === 0)) return null;
    const q = debouncedQuery.trim().toLowerCase();
    const stmts: StmtBlock[] = chapters.flatMap((ch) => ch.blocks.filter((b): b is StmtBlock => b.t === 'stmt'));
    return stmts.filter((b) => {
      if (statusFilter.size && !statusFilter.has(b.enrich?.lean_status || 'empty')) return false;
      if (q && !(searchText.get(b) || '').includes(q)) return false;
      return true;
    });
  }, [data, debouncedQuery, statusFilter, chapters, searchText]);

  function onSetView(v: ViewName) {
    if (v === 'graph') {
      setGraphOpen(true);
      return;
    }
    setView(v);
  }

  // live header stats — total/mathlib/lean/sorry counts + formalized % —
  // ported from the original's `stats()`.
  const stats = useMemo(() => {
    const es = data?.entries || [];
    const c = { total: es.length, mathlib_ok: 0, lean_ok: 0, sorry: 0 };
    for (const e of es) {
      if (e.lean_status === 'mathlib_ok') c.mathlib_ok++;
      else if (e.lean_status === 'lean_ok') c.lean_ok++;
      else if (e.lean_status === 'sorry') c.sorry++;
    }
    const pct = Math.round((100 * (c.lean_ok + c.mathlib_ok)) / Math.max(1, c.total));
    return { ...c, pct };
  }, [data]);

  if (error) return <div className="page-error">Couldn't load this project: {error}</div>;
  if (!data) return <div className="page-loading">Loading…</div>;

  const showResults = view === 'doc' && !!filtered;

  return (
    <div className="project-page">
      <HoverPreview data={data} root={root} onNavigate={navigate} />
      {graphOpen && (
        <GraphModal
          data={data}
          root={root}
          selectedId={graphSelectedId}
          onSelect={setGraphSelectedId}
          onClose={() => setGraphOpen(false)}
          usedByMap={usedByMap}
          byId={byId}
        />
      )}
      <header className="project-header">
        <div className="project-htop">
          <a href="#/" className="project-home" title="All projects">
            &larr; All projects
          </a>
          <h1>{data.docTitle || data.title}</h1>
          <span className="sub">blueprint</span>
          <div className="project-stats">
            <span className="pstat">
              <b>{stats.total}</b> statements
            </span>
            <span className="pstat" style={{ color: 'var(--mathlib)' }}>
              <b>{stats.mathlib_ok}</b> mathlib
            </span>
            <span className="pstat" style={{ color: 'var(--lean)' }}>
              <b>{stats.lean_ok}</b> lean
            </span>
            <span className="pstat" style={{ color: 'var(--sorry)' }}>
              <b>{stats.sorry}</b> sorry
            </span>
            <span className="pstat">
              <b>{stats.pct}%</b> formalized
              <span className="pbar">
                <i style={{ width: `${stats.pct}%` }} />
              </span>
            </span>
          </div>
        </div>
      </header>

      <div className="doc-wrap">
        <Toc
          chapters={chapters}
          refs={refs}
          curCh={curCh}
          onGoto={gotoChapter}
          onGotoSection={gotoSection}
          query={query}
          onQuery={onQueryChange}
          statusFilter={statusFilter}
          onToggleStatus={toggleStatus}
          view={view}
          graphOpen={graphOpen}
          onSetView={onSetView}
        />

        <main className="doc-main">
          {view === 'summary' ? (
            <Summary entries={data.entries} chapters={chapters} refs={refs} onSelect={navigate} onGotoChapter={gotoChapter} />
          ) : view === 'biblio' ? (
            <Bibliography bib={data.bib} entries={data.entries} refs={refs} onSelect={navigate} flashKey={flashBibKey} />
          ) : showResults && filtered ? (
            <div className="doc">
              <h2 className="ch">Results · {filtered.length}</h2>
              {filtered.length === 0 && <p className="ro">No statements match.</p>}
              {filtered.slice(0, MAX_RESULTS).map((b) => (
                <StmtBox
                  key={b.id}
                  b={b}
                  refs={refs}
                  macros={data.macros}
                  usedByCount={(b.id && usedByCounts.get(b.id)) || 0}
                  selected={selectedId === b.id}
                  onSelect={navigate}
                  onNavigate={navigate}
                  onCite={onCite}
                />
              ))}
              {filtered.length > MAX_RESULTS && (
                <p className="ro">
                  Showing the first {MAX_RESULTS} of {filtered.length} matches — narrow the search to see the rest.
                </p>
              )}
            </div>
          ) : view === 'overview' && chapters.length > 0 ? (
            <Overview docTitle={data.docTitle} docAuthor={data.docAuthor} chapters={chapters} onGoto={navigate} />
          ) : chapters.length > 0 ? (
            <ChapterView
              key={curCh} /* fresh progressive-hydration state per chapter */
              chapter={chapters[curCh]}
              refs={refs}
              cites={cites}
              macros={data.macros}
              usedBy={usedByCounts}
              selectedId={selectedId}
              onSelect={navigate}
              onNavigate={navigate}
              onCite={onCite}
              anchor={anchor}
            />
          ) : (
            <FlatList data={data} onSelect={navigate} />
          )}
        </main>

        <Outline chapter={chapters[curCh] || null} selectedId={selectedId} onSelect={navigate} />
      </div>
    </div>
  );
}

function FlatList({ data, onSelect }: { data: ProjectData; onSelect: (id: string) => void }) {
  return (
    <div className="doc">
      <h2 className="ch">{data.title}</h2>
      {data.entries.map((e) => (
        <div className="stmt" key={e.id} onClick={() => onSelect(e.id)}>
          <div className="sh">
            <span className="tag">{e.kind}</span>
            <span className="st">{e.title}</span>
            <span className="badges">
              <span className={`b b-${e.lean_status}`}>{e.lean_status.replace('_', ' ')}</span>
            </span>
          </div>
          <div className="sbody">{e.body}</div>
        </div>
      ))}
    </div>
  );
}
