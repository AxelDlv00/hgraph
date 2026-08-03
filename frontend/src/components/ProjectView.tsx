import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Chapter, ProjectData, ProjectGraphData, Dep, StmtBlock } from '../types';
import { ChapterView } from './ChapterView';
import { Toc, type ViewName } from './Toc';
import { Outline } from './Outline';
import { Overview } from './Overview';
import { StmtBox } from './StmtBox';
import { HoverPreview } from './HoverPreview';
import { Summary } from './Summary';
import { Bibliography } from './Bibliography';
import { ContentPage } from './ContentPage';
import { citeNums, plainTex, setExtRefs } from '../latex';
import { setDefaultMacros } from '../typeset';
import {
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  RotateCw,
  X,
} from 'lucide-react';

const GraphModal = lazy(() =>
  import('./GraphModal').then((module) => ({ default: module.GraphModal })),
);

// how many search results render at once — past this, a broad query (one
// letter, or a bare status chip on a large blueprint) would typeset hundreds
// of KaTeX boxes for content nobody scrolls through
const MAX_RESULTS = 120;

function projectAsset(root: string, path: string): string {
  return `${root.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`;
}

async function fetchJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}

function useStoredPanelState(key: string): [boolean, () => void] {
  const [open, setOpen] = useState(() => {
    try {
      const stored = window.localStorage.getItem(key);
      return stored === null ? true : stored === 'true';
    } catch {
      return true;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(key, String(open));
    } catch {
      // Storage can be disabled; the controls still work for this session.
    }
  }, [key, open]);

  return [open, () => setOpen((current) => !current)];
}

function flashEl(id: string) {
  requestAnimationFrame(() => {
    let el = document.getElementById(id);
    if (!el) return;
    // an equation marker has no box of its own — flash the display it precedes
    if (el.classList.contains('eqa')) el = (el.nextElementSibling as HTMLElement) || el;
    el.classList.add('flash');
    window.setTimeout(() => el!.classList.remove('flash'), 1700);
  });
}

function GraphPending({
  error,
  onRetry,
  onClose,
}: {
  error?: string | null;
  onRetry: () => void;
  onClose: () => void;
}) {
  return (
    <div className="graph-modal">
      <div className="gm-bar">
        <h2>Dependency graph</h2>
        <span className="sp" />
        {error && (
          <button type="button" className="gm-btn" onClick={onRetry} title="Retry graph loading" aria-label="Retry graph loading">
            <RotateCw size={16} aria-hidden="true" />
          </button>
        )}
        <button type="button" className="gm-btn" onClick={onClose} title="Close graph" aria-label="Close graph">
          <X size={17} aria-hidden="true" />
        </button>
      </div>
      <div className={error ? 'page-error' : 'page-loading'}>
        {error ? `Couldn't load the dependency graph: ${error}` : 'Preparing dependency graph…'}
      </div>
    </div>
  );
}

function ContentPending({
  label,
  error,
  onRetry,
}: {
  label: string;
  error?: string | null;
  onRetry: () => void;
}) {
  return (
    <div className="doc">
      <div className={error ? 'page-error' : 'page-loading'}>
        <span>{error ? `Couldn't load ${label}: ${error}` : `Loading ${label}…`}</span>
        {error && (
          <button type="button" className="gm-btn" onClick={onRetry} title={`Retry ${label}`} aria-label={`Retry ${label}`}>
            <RotateCw size={16} aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
}

export function ProjectView({ root, initialLocator }: { root: string; initialLocator?: string | null }) {
  const [data, setData] = useState<ProjectData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadedChapters, setLoadedChapters] = useState<Set<number>>(new Set());
  const [loadingChapters, setLoadingChapters] = useState<Set<number>>(new Set());
  const [chapterErrors, setChapterErrors] = useState<Map<number, string>>(new Map());
  const chapterRequests = useRef(new Map<number, Promise<Chapter>>());
  const extrefsRequest = useRef<Promise<void> | null>(null);
  const [graphData, setGraphData] = useState<ProjectGraphData | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);
  const graphRequest = useRef<Promise<void> | null>(null);
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
  const [leftPanelOpen, toggleLeftPanel] = useStoredPanelState('hgraph:blueprint:left-panel');
  const [rightPanelOpen, toggleRightPanel] = useStoredPanelState('hgraph:blueprint:right-panel');

  // project macros apply to every typeset on the page, including titles that
  // don't thread a macros prop (TOC, overview, summary, bibliography); the
  // cross-project `\citeext` targets are project-global the same way.
  useEffect(() => {
    setDefaultMacros(data?.macros);
    setExtRefs(data?.extrefs);
    return () => { setDefaultMacros(null); setExtRefs(null); };
  }, [data?.macros, data?.extrefs]);

  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError(null);
    setLoadedChapters(new Set());
    setLoadingChapters(new Set());
    setChapterErrors(new Map());
    setGraphData(null);
    setGraphError(null);
    graphRequest.current = null;
    chapterRequests.current.clear();
    extrefsRequest.current = null;

    async function load() {
      let project: ProjectData;
      try {
        project = await fetchJson<ProjectData>(projectAsset(root, 'project.json'), controller.signal);
      } catch (shellError) {
        if (controller.signal.aborted) return;
        try {
          // Compatibility with sites generated before incremental payloads.
          project = await fetchJson<ProjectData>(projectAsset(root, 'data.json'), controller.signal);
        } catch (fallbackError) {
          if (!controller.signal.aborted) setError(String(fallbackError || shellError));
          return;
        }
      }
      if (controller.signal.aborted) return;
      setData(project);
      if (!project.lazy?.chapters) {
        setLoadedChapters(new Set((project.chapters || []).map((_, index) => index)));
      }
    }

    void load();
    return () => controller.abort();
  }, [root]);

  const loadExtrefs = useCallback((): Promise<void> => {
    const path = data?.lazy?.extrefs;
    if (!data || !path || data.extrefs) return Promise.resolve();
    if (extrefsRequest.current) return extrefsRequest.current;
    const request = fetchJson<NonNullable<ProjectData['extrefs']>>(projectAsset(root, path))
      .then((extrefs) => setData((current) => current ? { ...current, extrefs } : current))
      .catch(() => {
        // Cross-project citation labels are supplementary. A missing legacy
        // endpoint must not prevent the chapter itself from opening.
        setData((current) => current ? { ...current, extrefs: {} } : current);
      });
    extrefsRequest.current = request;
    return request;
  }, [data, root]);

  const loadChapter = useCallback((index: number): Promise<Chapter> => {
    const current = data?.chapters?.[index];
    const pattern = data?.lazy?.chapters;
    if (!current) return Promise.reject(new Error(`Unknown chapter ${index + 1}`));
    if (!pattern || loadedChapters.has(index)) return Promise.resolve(current);
    const pending = chapterRequests.current.get(index);
    if (pending) return pending;

    setLoadingChapters((values) => new Set(values).add(index));
    setChapterErrors((values) => {
      const next = new Map(values);
      next.delete(index);
      return next;
    });
    // Reference labels may take longer in a workspace because they span sibling
    // projects. Start them alongside the chapter, but never hold its first paint.
    void loadExtrefs();
    const request = fetchJson<Chapter>(projectAsset(root, pattern.replace('{index}', String(index))))
      .then((chapter) => {
        setData((value) => {
          if (!value?.chapters) return value;
          const chapters = value.chapters.slice();
          chapters[index] = chapter;
          const hydrated = new Map(
            chapter.blocks
              .filter((block): block is StmtBlock => block.t === 'stmt' && !!block.id)
              .map((block) => [block.id!, block]),
          );
          const entries = value.entries.map((entry) => {
            const block = hydrated.get(entry.id);
            return block?.enrich
              ? { ...entry, body: block.body, ...block.enrich }
              : entry;
          });
          return { ...value, chapters, entries };
        });
        setLoadedChapters((values) => new Set(values).add(index));
        return chapter;
      })
      .catch((reason) => {
        const message = String(reason);
        setChapterErrors((values) => new Map(values).set(index, message));
        throw reason;
      })
      .finally(() => {
        chapterRequests.current.delete(index);
        setLoadingChapters((values) => {
          const next = new Set(values);
          next.delete(index);
          return next;
        });
      });
    chapterRequests.current.set(index, request);
    return request;
  }, [data, loadExtrefs, loadedChapters, root]);

  const loadAllChapters = useCallback(async () => {
    const chapters = data?.chapters || [];
    await Promise.all(chapters.map((_, index) => loadChapter(index)));
  }, [data?.chapters, loadChapter]);

  const loadGraph = useCallback((): Promise<void> => {
    if (!data || graphData) return Promise.resolve();
    if (graphRequest.current) return graphRequest.current;
    if (!data.lazy?.graph) {
      setGraphData({ entries: data.entries, gvsvg: data.gvsvg });
      return Promise.resolve();
    }
    setGraphLoading(true);
    setGraphError(null);
    const request = fetchJson<ProjectGraphData>(projectAsset(root, data.lazy.graph))
      .then(setGraphData)
      .catch((reason) => {
        setGraphError(String(reason));
        throw reason;
      })
      .finally(() => {
        graphRequest.current = null;
        setGraphLoading(false);
      });
    graphRequest.current = request;
    return request;
  }, [data, graphData, root]);

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

  const entries = useMemo(() => graphData?.entries || data?.entries || [], [data?.entries, graphData]);
  const graphProjectData = useMemo<ProjectData | null>(
    () => data && graphData ? { ...data, entries: graphData.entries, gvsvg: graphData.gvsvg } : null,
    [data, graphData],
  );

  // reverse dependency index ("used by"), computed once per payload
  const usedByMap = useMemo(() => {
    const map = new Map<string, Dep[]>();
    for (const e of entries) {
      for (const d of e.deps) {
        const back: Dep = { id: e.id, title: e.title, label: e.label, type: d.type };
        if (!map.has(d.id)) map.set(d.id, []);
        map.get(d.id)!.push(back);
      }
    }
    return map;
  }, [entries]);
  const byId = useMemo(() => new Map(entries.map((e) => [e.id, e])), [entries]);

  // stable identities per fetch — BlockView is memoised on these
  const refs = useMemo(() => data?.refs || {}, [data]);
  const chapters = useMemo(() => data?.chapters || [], [data]);
  const allChaptersLoaded = !data?.lazy?.chapters
    || chapters.every((_, index) => loadedChapters.has(index));
  // \cite{key} renders as its bibliography number, the way LaTeX numbers it
  const cites = useMemo(() => citeNums(data?.bib), [data]);

  // Scroll to any element within a chapter, switching to it first — the target
  // of a chapter/section/equation `\ref`, and of the bibliography's "Cited in".
  // An empty `elementId` just opens the chapter at its top.
  const gotoAnchor = useCallback((chapterIndex: number, elementId: string) => {
    setView('doc');
    setQuery('');
    setStatusFilter(new Set());
    setCurCh(chapterIndex);
    setSelectedId(null);
    setAnchor(elementId || null);
    void loadChapter(chapterIndex).then(() => {
      if (!elementId) return;
      requestAnimationFrame(() => {
        document.getElementById(elementId)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        flashEl(elementId);
      });
    }).catch(() => undefined);
  }, [loadChapter]);

  // useCallback: navigate is a prop of every memoised BlockView — a fresh
  // closure per render would defeat the memo and re-render whole chapters
  const navigate = useCallback((id: string) => {
    // a "<chapter index>:<element id>" locator rather than a node id — what
    // latex.ts's xref emits for the refs that have no graph node behind them
    const locator = id.match(/^(\d+):(.*)$/);
    if (locator) return gotoAnchor(Number(locator[1]), locator[2]);
    setView('doc');
    if (!chapters.length) {
      setSelectedId(id);
      return;
    }
    setQuery('');
    setStatusFilter(new Set());
    const loc = data?.loc?.[id];
    const chapterIndex = loc ?? curCh;
    if (loc !== undefined && loc !== curCh) setCurCh(loc);
    setSelectedId(id);
    setAnchor(`stmt-${id}`);
    void loadChapter(chapterIndex).then(() => {
      requestAnimationFrame(() => {
        document.getElementById(`stmt-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        flashEl(`stmt-${id}`);
      });
    }).catch(() => undefined);
    const e = data?.entries.find((x) => x.id === id);
    setHash(e?.label || id);
  }, [data, chapters, curCh, setHash, gotoAnchor, loadChapter]);

  const openInGraph = useCallback((id: string) => {
    setGraphSelectedId(id);
    setGraphOpen(true);
    void loadGraph().catch(() => undefined);
  }, [loadGraph]);

  const openInBlueprint = useCallback((id: string) => {
    setGraphOpen(false);
    setGraphSelectedId(null);
    navigate(id);
  }, [navigate]);

  function gotoSection(chapterIndex: number, num: string) {
    setView('doc');
    setCurCh(chapterIndex);
    setSelectedId(null);
    setAnchor(`sec-${num}`);
    void loadChapter(chapterIndex).then(() => {
      requestAnimationFrame(() => {
        document.getElementById(`sec-${num}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }).catch(() => undefined);
  }

  // jump to a specific citing block from the bibliography's "Cited in" list —
  // like navigate(), but the target is any block (prose/proof included), keyed
  // by its ChapterView anchor rather than a statement id
  const gotoLoc = useCallback((chapterIndex: number, _blockIndex: number, blockAnchor: string) => {
    gotoAnchor(chapterIndex, blockAnchor);
  }, [gotoAnchor]);

  const gotoChapter = useCallback((chapterIndex: number) => {
    setView('doc');
    setQuery('');
    setStatusFilter(new Set());
    setCurCh(chapterIndex);
    setSelectedId(null);
    setAnchor(null);
    setHash(`ch-${chapterIndex + 1}`);
    void loadChapter(chapterIndex).catch(() => undefined);
  }, [loadChapter, setHash]);

  // honour an incoming "#/<root>#<locator>" once the data's loaded — same
  // syntax the original's `gotoHash` understood (a chapter "ch-N"/"chapter-N",
  // an optional "stmt-" prefix, or a raw \label / node id).
  const handledLocator = useRef<string | null>(null);
  useEffect(() => {
    if (!data || !initialLocator) return;
    if (handledLocator.current === initialLocator) return;
    handledLocator.current = initialLocator;
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
    // re-run on locator changes too: an external link can change just the
    // "#…#<locator>" part while staying in the same project (our own setHash
    // uses replaceState, which fires no hashchange, so it never loops this)
  }, [data, initialLocator, navigate, gotoChapter]);

  function toggleStatus(s: string) {
    setView('doc');
    void loadAllChapters().catch(() => undefined);
    const next = new Set(statusFilter);
    if (next.has(s)) next.delete(s);
    else next.add(s);
    setStatusFilter(next);
  }

  function onQueryChange(q: string) {
    setView('doc');
    setQuery(q);
    if (q.trim() || statusFilter.size) void loadAllChapters().catch(() => undefined);
  }

  const [flashBibKey, setFlashBibKey] = useState<string | null>(null);
  const onCite = useCallback((key: string) => {
    setView('biblio');
    setFlashBibKey(key);
    void loadAllChapters().then(() => {
      requestAnimationFrame(() => {
        document.querySelector(`.bibitem[data-key="${CSS.escape(key)}"]`)?.scrollIntoView({ block: 'center' });
      });
      window.setTimeout(() => setFlashBibKey(null), 1700);
    }).catch(() => undefined);
  }, [loadAllChapters]);

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
    if (!data || !allChaptersLoaded || (!debouncedQuery.trim() && statusFilter.size === 0)) return null;
    const q = debouncedQuery.trim().toLowerCase();
    const stmts: StmtBlock[] = chapters.flatMap((ch) => ch.blocks.filter((b): b is StmtBlock => b.t === 'stmt'));
    return stmts.filter((b) => {
      if (statusFilter.size && !statusFilter.has(b.enrich?.lean_status || 'empty')) return false;
      if (q && !(searchText.get(b) || '').includes(q)) return false;
      return true;
    });
  }, [data, allChaptersLoaded, debouncedQuery, statusFilter, chapters, searchText]);

  function onSetView(v: ViewName) {
    if (v === 'graph') {
      setGraphOpen(true);
      void loadGraph().catch(() => undefined);
      return;
    }
    setView(v);
    if (v === 'biblio') void loadAllChapters().catch(() => undefined);
  }

  // live header stats — total/mathlib/lean/sorry counts + formalized % —
  // ported from the original's `stats()`.
  const stats = useMemo(() => {
    const es = entries;
    const c = { total: es.length, mathlib_ok: 0, lean_ok: 0, sorry: 0 };
    for (const e of es) {
      if (e.lean_status === 'mathlib_ok') c.mathlib_ok++;
      else if (e.lean_status === 'lean_ok') c.lean_ok++;
      else if (e.lean_status === 'sorry') c.sorry++;
    }
    const pct = Math.round((100 * (c.lean_ok + c.mathlib_ok)) / Math.max(1, c.total));
    return { ...c, pct };
  }, [entries]);

  if (error) return <div className="page-error">Couldn't load this project: {error}</div>;
  if (!data) return <div className="page-loading">Loading…</div>;

  const showResults = view === 'doc' && !!filtered;
  const needsAllChapters = view === 'biblio'
    || (view === 'doc' && (!!query.trim() || statusFilter.size > 0));
  const allLoadError = Array.from(chapterErrors.values())[0] || null;
  const chaptersAreLoading = loadingChapters.size > 0;
  const currentChapterLoaded = !data.lazy?.chapters || loadedChapters.has(curCh);
  const currentChapterError = chapterErrors.get(curCh) || null;
  const customTabs = data.customTabs ?? [];
  const activeCustom = customTabs.find((c) => c.id === view);
  // a project's configured accent recolours its whole blueprint view — every
  // accent in index.css reads `var(--accent)`, so overriding it here on the
  // page root cascades to nav, chapters, pills and hovers in one line.
  const accentStyle = data.theme
    ? ({ '--accent': data.theme.accent } as React.CSSProperties)
    : undefined;

  return (
    <div className="project-page" style={accentStyle}>
      {/* while the graph modal is open, clicks in its pinned mini-graph popup
          must select within the modal, not silently change the doc view behind it */}
      <HoverPreview data={graphProjectData || data} root={root} onNavigate={graphOpen ? openInGraph : navigate} />
      {graphOpen && graphProjectData && (
        <Suspense
          fallback={(
            <GraphPending
              onRetry={() => { void loadGraph().catch(() => undefined); }}
              onClose={() => setGraphOpen(false)}
            />
          )}
        >
          <GraphModal
            data={graphProjectData}
            root={root}
            selectedId={graphSelectedId}
            onSelect={setGraphSelectedId}
            onOpenBlueprint={openInBlueprint}
            onClose={() => setGraphOpen(false)}
            usedByMap={usedByMap}
            byId={byId}
          />
        </Suspense>
      )}
      {graphOpen && !graphProjectData && (
        <GraphPending
          error={graphLoading ? null : graphError}
          onRetry={() => { void loadGraph().catch(() => undefined); }}
          onClose={() => setGraphOpen(false)}
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

      <div
        className={`doc-wrap${leftPanelOpen ? '' : ' nav-collapsed'}${rightPanelOpen ? '' : ' outline-collapsed'}`}
      >
        <div className="panel-rails" aria-label="Blueprint panels">
          <button
            type="button"
            className="panel-toggle panel-rail panel-rail-left"
            onClick={toggleLeftPanel}
            aria-controls="blueprint-navigation"
            aria-expanded={leftPanelOpen}
            title={leftPanelOpen ? 'Collapse navigation panel' : 'Expand navigation panel'}
          >
            {leftPanelOpen ? <PanelLeftClose aria-hidden="true" /> : <PanelLeftOpen aria-hidden="true" />}
            <span className="sr-only">{leftPanelOpen ? 'Collapse' : 'Expand'} navigation panel</span>
          </button>
          <button
            type="button"
            className="panel-toggle panel-rail panel-rail-right"
            onClick={toggleRightPanel}
            aria-controls="blueprint-outline"
            aria-expanded={rightPanelOpen}
            title={rightPanelOpen ? 'Collapse chapter outline' : 'Expand chapter outline'}
          >
            {rightPanelOpen ? <PanelRightClose aria-hidden="true" /> : <PanelRightOpen aria-hidden="true" />}
            <span className="sr-only">{rightPanelOpen ? 'Collapse' : 'Expand'} chapter outline</span>
          </button>
        </div>
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
          customTabs={customTabs}
        />

        <main className="doc-main">
          {activeCustom ? (
            <ContentPage html={activeCustom.html} className="doc" />
          ) : view === 'summary' ? (
            <Summary entries={entries} chapters={chapters} refs={refs} onSelect={navigate} onGotoChapter={gotoChapter} />
          ) : needsAllChapters && !allChaptersLoaded ? (
            <ContentPending
              label={view === 'biblio' ? 'bibliography references' : 'search index'}
              error={chaptersAreLoading ? null : allLoadError}
              onRetry={() => { void loadAllChapters().catch(() => undefined); }}
            />
          ) : view === 'biblio' ? (
            <Bibliography bib={data.bib} chapters={chapters} onGotoLoc={gotoLoc} flashKey={flashBibKey} />
          ) : showResults && filtered ? (
            <div className="doc">
              <h2 className="ch">Results · {filtered.length}</h2>
              {filtered.length === 0 && <p className="ro">No statements match.</p>}
              {filtered.slice(0, MAX_RESULTS).map((b) => (
                <StmtBox
                  key={b.id}
                  b={b}
                  refs={refs}
                  cites={cites}
                  macros={data.macros}
                  usedBy={(b.id && usedByMap.get(b.id)) || []}
                  selected={selectedId === b.id}
                  onSelect={navigate}
                  onNavigate={navigate}
                  onOpenGraph={openInGraph}
                  onCite={onCite}
                  root={root}
                  repo={data.repo}
                />
              ))}
              {filtered.length > MAX_RESULTS && (
                <p className="ro">
                  Showing the first {MAX_RESULTS} of {filtered.length} matches — narrow the search to see the rest.
                </p>
              )}
            </div>
          ) : view === 'overview' && chapters.length > 0 ? (
            <Overview
              docTitle={data.docTitle}
              docAuthor={data.docAuthor}
              chapters={chapters}
              refs={refs}
              onGoto={navigate}
              onGotoChapter={gotoChapter}
              onGotoSection={gotoSection}
            />
          ) : chapters.length > 0 && !currentChapterLoaded ? (
            <ContentPending
              label={`chapter ${chapters[curCh]?.num || curCh + 1}`}
              error={loadingChapters.has(curCh) ? null : currentChapterError}
              onRetry={() => { void loadChapter(curCh).catch(() => undefined); }}
            />
          ) : chapters.length > 0 ? (
            <ChapterView
              key={curCh} /* fresh progressive-hydration state per chapter */
              chapter={chapters[curCh]}
              refs={refs}
              cites={cites}
              macros={data.macros}
              usedBy={usedByMap}
              selectedId={selectedId}
              onSelect={navigate}
              onNavigate={navigate}
              onGotoSection={(num) => gotoSection(curCh, num)}
              onOpenGraph={openInGraph}
              onCite={onCite}
              anchor={anchor}
              root={root}
              repo={data.repo}
            />
          ) : (
            <FlatList data={data} onSelect={navigate} onOpenGraph={openInGraph} />
          )}
        </main>

        <Outline chapter={chapters[curCh] || null} selectedId={selectedId} onSelect={navigate} />
      </div>
    </div>
  );
}

function FlatList({
  data,
  onSelect,
  onOpenGraph,
}: {
  data: ProjectData;
  onSelect: (id: string) => void;
  onOpenGraph: (id: string) => void;
}) {
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
              <button
                type="button"
                className="entry-graph-btn"
                onClick={(event) => {
                  event.stopPropagation();
                  onOpenGraph(e.id);
                }}
                title="Open this declaration in the dependency graph"
                aria-label="Open in graph"
              >
                <Network size={14} strokeWidth={2} aria-hidden="true" />
              </button>
            </span>
          </div>
          <div className="sbody">{e.body}</div>
        </div>
      ))}
    </div>
  );
}
