import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { Dep, Entry, ProjectData } from '../types';
import { buildGraphModel, dotMixed, CHAPTER_ID_RE, type GraphModel } from '../graphDot';
import { layoutDot, cachedLayout, prefetchLayouts } from '../vizInstance';
import { citeNums } from '../latex';
import { GraphLegend } from './GraphLegend';
import { StatementCard } from './StatementCard';

const STATUS_CHIPS: { f: string; label: string }[] = [
  { f: 'mathlib_ok', label: 'mathlib' },
  { f: 'lean_ok', label: 'lean' },
  { f: 'sorry', label: 'sorry' },
  { f: 'empty', label: 'no lean' },
];

const SCALE_MIN = 0.05;
const SCALE_MAX = 6;

function statusPasses(e: Entry, statusFilter: ReadonlySet<string>, q: string): boolean {
  if (statusFilter.size && !statusFilter.has(e.lean_status)) return false;
  if (q && !((e.title || '') + ' ' + (e.label || '')).toLowerCase().includes(q)) return false;
  return true;
}

/**
 * The full-screen dependency-graph overlay — ported from the original's
 * `#graphmodal`. Every chapter starts collapsed into one purple aggregate
 * box; clicking one opens it into its statements while every *other* chapter
 * stays a box, so cross-chapter edges still land somewhere visible. Exactly
 * one chapter is open at a time — opening another switches to it, and
 * clicking the open chapter's background closes it again. Each
 * expand/collapse/detail-level change regenerates a fresh DOT graph and
 * re-lays it out with Graphviz — a real re-layout, not hide/show on a stale
 * one — in a Web Worker (see vizInstance.ts), cached per DOT string, and
 * prefetched per chapter in idle time, so opening a chapter is usually
 * instant and never freezes the page. The all-collapsed starting state uses
 * the build-time-precomputed SVG (`data.gvsvg.groups`) when present, exactly
 * as the original's `gmPreSvg` did — and falls back to a live layout of the
 * same overview when the build had no `dot` binary.
 *
 * Pan/zoom deliberately bypass React state: the transform lives in a ref and
 * is written straight to the inner element's style inside rAF, so dragging or
 * scrolling never re-renders (let alone re-wires) a many-hundred-node SVG.
 * Trackpad two-finger scroll pans; pinch (which browsers deliver as a
 * ctrlKey wheel) or ctrl/cmd+scroll zooms, anchored at the cursor.
 */
export function GraphModal({
  data,
  root,
  selectedId,
  onSelect,
  onClose,
  usedByMap,
  byId,
}: {
  data: ProjectData;
  root: string;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onClose: () => void;
  usedByMap: Map<string, Dep[]>;
  byId: Map<string, Entry>;
}) {
  const model: GraphModel = useMemo(() => buildGraphModel(data), [data]);
  // so the side panel renders \ref/\cite exactly as the document does
  const cites = useMemo(() => citeNums(data.bib), [data]);

  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [lvlMax, setLvlMax] = useState(2);
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState('');
  const [svg, setSvg] = useState<string | null>(data.gvsvg?.groups || null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [chapterPick, setChapterPick] = useState('');

  const wrapRef = useRef<HTMLDivElement | null>(null);
  const innerRef = useRef<HTMLDivElement | null>(null);

  // --- pan/zoom: refs + direct style writes, never React state --------------
  const tRef = useRef({ x: 0, y: 0, scale: 1 });
  const rafRef = useRef(0);
  const dragRef = useRef<{ id: number; x: number; y: number; moved: number; captured: boolean } | null>(null);
  const suppressClick = useRef(false);

  function applyTransform() {
    rafRef.current = 0;
    const el = innerRef.current;
    if (!el) return;
    const t = tRef.current;
    el.style.transform = `translate(${t.x}px, ${t.y}px) scale(${t.scale})`;
  }
  function scheduleApply() {
    if (!rafRef.current) rafRef.current = requestAnimationFrame(applyTransform);
  }
  useEffect(() => () => cancelAnimationFrame(rafRef.current), []);

  /** Scale so the whole graph fits the canvas (never above natural size). */
  function fitToView() {
    const canvas = wrapRef.current;
    const el = innerRef.current;
    if (!canvas || !el) return;
    let scale = 1;
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    if (w > 0 && h > 0) scale = Math.min(canvas.clientWidth / w, canvas.clientHeight / h, 1) * 0.96;
    tRef.current = { x: 0, y: 0, scale: Math.max(scale, SCALE_MIN) };
    scheduleApply();
  }

  /** Zoom by `factor` keeping the content under (clientX, clientY) fixed. */
  function zoomAt(clientX: number, clientY: number, factor: number) {
    const canvas = wrapRef.current;
    if (!canvas) return;
    const t = tRef.current;
    const scale = Math.min(SCALE_MAX, Math.max(SCALE_MIN, t.scale * factor));
    const k = scale / t.scale;
    if (k === 1) return;
    // the inner div is flex-centred with transform-origin at its centre, so
    // its centre sits at the canvas centre + the current translation
    const r = canvas.getBoundingClientRect();
    const cx = r.left + r.width / 2 + t.x;
    const cy = r.top + r.height / 2 + t.y;
    tRef.current = { x: t.x + (clientX - cx) * (1 - k), y: t.y + (clientY - cy) * (1 - k), scale };
    scheduleApply();
  }

  function onPointerDown(e: React.PointerEvent) {
    if (e.button !== 0) return;
    suppressClick.current = false;
    // NOTE: don't capture the pointer here — capturing retargets the eventual
    // `click` to the canvas, which would break node/cluster clicks (they're
    // delegated off e.target). Capture only once an actual drag has started.
    dragRef.current = { id: e.pointerId, x: e.clientX, y: e.clientY, moved: 0, captured: false };
  }
  function onPointerMove(e: React.PointerEvent) {
    const d = dragRef.current;
    if (!d || d.id !== e.pointerId) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    d.x = e.clientX;
    d.y = e.clientY;
    d.moved += Math.abs(dx) + Math.abs(dy);
    if (!d.captured && d.moved > 3) {
      // a real drag: from here on, keep the pan alive outside the canvas too
      // (the click this drag ends in is suppressed in endDrag anyway)
      wrapRef.current?.setPointerCapture(e.pointerId);
      d.captured = true;
    }
    const t = tRef.current;
    tRef.current = { ...t, x: t.x + dx, y: t.y + dy };
    scheduleApply();
  }
  function endDrag(e: React.PointerEvent) {
    const d = dragRef.current;
    if (d && d.id === e.pointerId) {
      // a real drag shouldn't ALSO select whatever node it ended on
      suppressClick.current = d.moved > 6;
      dragRef.current = null;
    }
  }

  const hasSvg = !!svg;

  // Wheel must be a native non-passive listener to preventDefault. Trackpad
  // two-finger scroll (and a plain mouse wheel) pans; pinch arrives as a
  // wheel event with ctrlKey set — that, or explicit ctrl/cmd+scroll, zooms.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const onWheel = (ev: WheelEvent) => {
      ev.preventDefault();
      const unit = ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? el.clientHeight : 1;
      if (ev.ctrlKey || ev.metaKey) {
        zoomAt(ev.clientX, ev.clientY, Math.exp(-ev.deltaY * unit * 0.0022));
      } else {
        const horizontal = ev.shiftKey && !ev.deltaX; // shift+wheel = sideways
        const dx = (horizontal ? ev.deltaY : ev.deltaX) * unit;
        const dy = (horizontal ? 0 : ev.deltaY) * unit;
        const t = tRef.current;
        tRef.current = { ...t, x: t.x - dx, y: t.y - dy };
        scheduleApply();
      }
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [hasSvg]);

  // --- render the current expand/level state -------------------------------
  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    if (expanded.size === 0 && data.gvsvg?.groups) {
      setSvg(data.gvsvg.groups);
      setLoading(false);
      return;
    }
    if (!model.nodes.length) {
      setSvg(null);
      setLoading(false);
      return;
    }
    // live layout — also the fallback for the all-collapsed overview when the
    // build had no `dot` binary (layout.py returns {} then)
    const dot = dotMixed(model, expanded, lvlMax);
    const hit = cachedLayout(dot);
    if (hit) {
      setSvg(hit);
      setLoading(false);
      return;
    }
    setLoading(true);
    layoutDot(dot)
      .then((out) => {
        if (!cancelled) setSvg(out);
      })
      .catch(() => {
        if (!cancelled) setLoadError('Graphviz failed to load — showing the last known graph.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [model, expanded, lvlMax, data.gvsvg]);

  // Chapters are only ever opened one at a time, so every layout this modal
  // can need is enumerable: warm them (worker, idle time) while the user
  // looks at the current graph — opening a chapter is then usually instant.
  useEffect(() => {
    if (!model.nodes.length) return;
    const dots: string[] = [];
    if (!data.gvsvg?.groups) dots.push(dotMixed(model, new Set<number>(), lvlMax));
    for (const c of model.chapters) if (c.count) dots.push(dotMixed(model, new Set<number>([c.key]), lvlMax));
    prefetchLayouts(dots);
  }, [model, lvlMax, data.gvsvg]);

  // fit the fresh layout to the canvas before paint (no flicker)
  useLayoutEffect(() => {
    fitToView();
  }, [svg]);

  // --- tag the rendered SVG --------------------------------------------------
  // data-nid / data-ch / data-edge drive the delegated click handler below,
  // the filter-dimming pass, and HoverPreview's `.node[data-nid]` hover
  // preview; the <title> elements they're read from are removed so the
  // browser doesn't add its own tooltips.
  //
  // No dependency array: React 19 re-sets `dangerouslySetInnerHTML` content
  // on ANY re-render of the element — even when `__html` is the very same
  // string — replacing the tagged <svg> with a raw one (verified against the
  // built bundle; the pre-rewrite code carried the same warning). The marker
  // guard below makes the re-run O(1) unless the DOM really was reset; and
  // since pan/zoom/drag write transforms through refs without re-rendering,
  // commits only happen on real state changes (clicks, filter edits) anyway.
  useLayoutEffect(() => {
    const svgEl = wrapRef.current?.querySelector('svg');
    if (!svgEl || svgEl.dataset.wired) return;
    svgEl.dataset.wired = '1';
    svgEl.querySelectorAll('g.node').forEach((g) => {
      const el = g as SVGGElement;
      const t = el.querySelector('title');
      el.dataset.nid = t ? (t.textContent || '').trim() : '';
      if (t) t.remove();
    });
    svgEl.querySelectorAll('g.cluster').forEach((g) => {
      const el = g as SVGGElement;
      const t = el.querySelector('title');
      const id = t ? (t.textContent || '').trim() : '';
      if (t) t.remove();
      const m = /^cluster_(\d+)$/.exec(id);
      if (m) el.dataset.ch = m[1];
    });
    svgEl.querySelectorAll('g.edge').forEach((g) => {
      const el = g as SVGGElement;
      const t = el.querySelector('title');
      if (t) {
        el.dataset.edge = (t.textContent || '').trim();
        t.remove();
      }
    });
  });

  // one delegated listener instead of one per node — re-renders never re-wire
  function onCanvasClick(e: React.MouseEvent) {
    if (suppressClick.current) {
      suppressClick.current = false;
      return;
    }
    const target = e.target as Element;
    const nodeEl = target.closest('g.node') as SVGGElement | null;
    if (nodeEl) {
      const id = nodeEl.dataset.nid || '';
      const m = CHAPTER_ID_RE.exec(id);
      if (m) {
        // exactly one chapter open at a time: opening this one closes any
        // other, so the graph stays about the chapter you asked for while
        // the rest remain as boxes for cross-chapter context
        setExpanded(new Set([Number(m[1])]));
      } else if (model.idx.has(id)) {
        onSelect(id);
      }
      return;
    }
    const clusterEl = target.closest('g.cluster') as SVGGElement | null;
    if (clusterEl?.dataset.ch != null) {
      const ch = Number(clusterEl.dataset.ch);
      setExpanded((s) => {
        const next = new Set(s);
        next.delete(ch);
        return next;
      });
    }
  }

  // --- status/search filter: dim non-matching nodes+edges, never hide (level
  // filtering already happened by regenerating the DOT above). No dependency
  // array for the same innerHTML-reset reason as the tagging pass above — a
  // reset wipes the inline opacities too, so re-apply after every commit
  // (it also reads the data-nid attributes that pass just (re-)wrote). ------
  useEffect(() => {
    const svgEl = wrapRef.current?.querySelector('svg');
    if (!svgEl) return;
    const q = query.trim().toLowerCase();
    const active = statusFilter.size > 0 || !!q;
    const passByNid = new Map<string, boolean>();
    svgEl.querySelectorAll('g.node').forEach((g) => {
      const el = g as SVGGElement;
      const id = el.dataset.nid || '';
      const ni = model.idx.get(id);
      const n = ni != null ? model.nodes[ni] : undefined;
      const pass = !n || statusPasses(n.e, statusFilter, q);
      if (n) passByNid.set(id, pass);
      el.style.opacity = active && n && !pass ? '0.12' : '1';
    });
    svgEl.querySelectorAll('g.edge').forEach((g) => {
      const el = g as SVGGElement;
      const parts = (el.dataset.edge || '').split('->').map((s) => s.trim());
      if (parts.length !== 2) return;
      const ap = passByNid.has(parts[0]) ? passByNid.get(parts[0]) : true;
      const bp = passByNid.has(parts[1]) ? passByNid.get(parts[1]) : true;
      el.style.opacity = active && (!ap || !bp) ? '0.06' : '1';
    });
  });

  // --- Escape: clear selection first, then close ----------------------------
  useEffect(() => {
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    function onKey(ev: KeyboardEvent) {
      if (ev.key !== 'Escape') return;
      if (selectedId != null) {
        onSelect(null);
        return;
      }
      onClose();
    }
    document.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      document.removeEventListener('keydown', onKey);
    };
  }, [selectedId, onSelect, onClose]);

  function toggleStatus(f: string) {
    setStatusFilter((s) => {
      const next = new Set(s);
      next.has(f) ? next.delete(f) : next.add(f);
      return next;
    });
  }

  const selectedEntry = selectedId ? byId.get(selectedId) || null : null;
  const q = query.trim().toLowerCase();
  const filterActive = statusFilter.size > 0 || !!q;
  const tot = model.nodes.length;
  const visCount = model.nodes.filter((n) => n.lvl <= lvlMax).length;
  const onCount = model.nodes.filter((n) => n.lvl <= lvlMax && statusPasses(n.e, statusFilter, q)).length;
  const countText = filterActive
    ? `${onCount} of ${tot} nodes`
    : lvlMax < 2
      ? `${visCount} of ${tot} nodes · ${['coarse', 'coarse+medium'][lvlMax]}`
      : `${tot} nodes · ${model.edges.length} edges`;
  const hint =
    (expanded.size === 0
      ? 'click a chapter to open it'
      : 'click a node to open it · click another chapter to switch to it, or this one’s background to close it') +
    ' · drag or scroll to pan · pinch or ctrl+scroll to zoom';

  return (
    <div className="graph-modal">
      <div className="gm-bar">
        <h2>Dependency graph</h2>
        <select
          className="gm-sel"
          title="Open a chapter — shows its statements; every other chapter stays a box"
          value={chapterPick}
          onChange={(e) => {
            const v = e.target.value;
            setChapterPick('');
            if (v !== '') setExpanded(new Set([Number(v)]));
          }}
        >
          <option value="">Open a chapter…</option>
          {model.chapters.map((c) => (
            <option key={c.key} value={c.key}>
              {c.label.slice(0, 42)}
            </option>
          ))}
        </select>
        <select
          className="gm-sel"
          title="Level of detail within expanded chapters (coarse = the most-depended-on statements only)"
          value={lvlMax}
          onChange={(e) => setLvlMax(Number(e.target.value))}
        >
          <option value={2}>Detail · all</option>
          <option value={1}>Detail · coarse + medium</option>
          <option value={0}>Detail · coarse only</option>
        </select>
        <input
          type="search"
          className="gm-q"
          placeholder="highlight…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {STATUS_CHIPS.map((c) => (
          <span key={c.f} className={`gm-chip${statusFilter.has(c.f) ? ' on' : ''}`} onClick={() => toggleStatus(c.f)}>
            {c.label}
          </span>
        ))}
        <span className="sp" />
        <button className="gm-btn" onClick={() => setExpanded(new Set())} disabled={!expanded.size} title="Close the open chapter and go back to the all-chapters overview">
          All chapters
        </button>
        <button className="gm-btn" onClick={fitToView} title="Fit the whole graph in view">
          Fit
        </button>
        <button className="gm-btn" onClick={onClose}>
          ✕ Close
        </button>
      </div>
      <div className="gm-body">
        <div className="gm-wrap">
          {svg ? (
            <div
              ref={wrapRef}
              className="gv-canvas"
              style={{ height: '100%' }}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={endDrag}
              onPointerCancel={endDrag}
              onClick={onCanvasClick}
            >
              <div ref={innerRef} className="gv-inner" dangerouslySetInnerHTML={{ __html: svg }} />
            </div>
          ) : (
            <div className="ro" style={{ margin: 16 }}>
              No dependency graph available for this project.
            </div>
          )}
          {loading && (
            <div className="gm-gvload">
              <div>Laying out…</div>
            </div>
          )}
          <div className="gm-float gm-count">
            <b>{countText}</b>
          </div>
          {svg && <GraphLegend mode={expanded.size === 0 ? 'groups' : 'full'} />}
          <div className="gm-float gm-hint">
            {hint}
            {loadError && (
              <>
                {' · '}
                <span style={{ color: 'var(--sorry)' }}>{loadError}</span>
              </>
            )}
          </div>
        </div>
        <div id="gm-side" className={selectedEntry ? '' : 'empty'}>
          {selectedEntry ? (
            <>
              <button className="gp-close gm-btn" onClick={() => onSelect(null)} title="Close (Esc)" aria-label="Close panel">
                ✕
              </button>
              <StatementCard
                entry={selectedEntry}
                usedBy={usedByMap.get(selectedEntry.id) || []}
                byId={byId}
                root={root}
                repo={data.repo}
                macros={data.macros}
                refs={data.refs}
                cites={cites}
                onNavigate={onSelect}
              />
            </>
          ) : (
            <div className="gp-empty">Select a node to see its statement, Lean &amp; dependencies.</div>
          )}
        </div>
      </div>
    </div>
  );
}
