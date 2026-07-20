import { useEffect, useRef, useState } from 'react';
import type { Dep, Entry, ProjectData } from '../types';
import { leanHi, esc, citeNums, proseHtml } from '../latex';
import { localDepGraph } from '../depgraph';
import { stmtPreviewHtml } from '../previews';
import { CHAPTER_ID_RE } from '../graphDot';
import { typesetMath } from '../typeset';

interface PvState {
  html: string;
  x: number;
  y: number;
}

/**
 * The floating hover-preview popup — ported from the original's `showPv`/
 * `stmtPv`/`leanPv`/`citePv`/`graphPv`/`leanTagPv`: hovering a `.ref[data-id]`
 * (cross-reference), `.leanref[data-name]` (a Lean declaration name), or
 * `.cite[data-cite]` (a bibliography citation) pops up a small preview near
 * the cursor after a short delay; clicking a `.mtag.pop[data-graph]`
 * ("uses N · used by N") or `.mtag.pop[data-lean]` ("Lean"/"mathlib") pins a
 * bigger popup with the local dependency mini-graph or the full Lean code —
 * these are click-only, never hover, matching the original. Pins on click,
 * dismisses on outside-click. One instance, mounted once, listening on the
 * whole document (event delegation, since the links themselves are raw HTML
 * from `detex`, not JSX).
 */
export function HoverPreview({ data, root, onNavigate }: { data: ProjectData; root: string; onNavigate: (id: string) => void }) {
  const [pv, setPv] = useState<PvState | null>(null);
  const pinnedRef = useRef(false);
  const showT = useRef<number | undefined>(undefined);
  const hideT = useRef<number | undefined>(undefined);
  const boxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const byId = new Map(data.entries.map((e) => [e.id, e]));
    const bib = new Map((data.bib || []).map((b, i) => [b.key, { ...b, _n: i + 1 }]));
    const rev = new Map<string, Entry[]>();
    for (const e of data.entries) {
      for (const d of e.deps) {
        const target = byId.get(d.id);
        if (!target) continue;
        if (!rev.has(d.id)) rev.set(d.id, []);
        rev.get(d.id)!.push(e);
      }
    }

    const cites = citeNums(data.bib);
    function stmtPreview(id: string): string | null {
      const e = byId.get(id);
      return e ? stmtPreviewHtml(e, data.refs || {}, cites) : null;
    }
    function leanPreview(name: string): string | null {
      for (const e of data.entries) {
        const l = e.lean.find((x) => x.name === name);
        if (l) return `<div class="pk">Lean · ${esc(name)}</div><pre class="lean">${leanHi(l.code)}</pre>`;
      }
      return null;
    }
    function citePreview(key: string): string {
      const b = bib.get(key);
      if (!b) return `<div class="pk">Reference</div><div style="margin-top:4px;color:var(--muted)">Unknown reference <b>${esc(key)}</b> (no matching .bib entry).</div>`;
      const fields = [b.author, b.title, b.year].filter(Boolean).join(', ');
      return `<div class="pk">Reference [${b._n}]</div><div style="margin-top:5px;line-height:1.5">${esc(fields)}${b.url ? ` <a href="${esc(b.url)}" target="_blank" rel="noopener">↗</a>` : ''}</div>`;
    }
    // preview for a bibliography "Cited in" link (`.citeloc[data-loc]`, encoded
    // "<chapterIndex>:<blockIndex>"): the citing passage itself, so the reader
    // sees *what* in the text cites the reference before clicking through
    const refs = data.refs || {};
    function locPreview(loc: string): string | null {
      const [ci, bi] = loc.split(':').map(Number);
      const b = data.chapters?.[ci]?.blocks?.[bi];
      if (!b) return null;
      if (b.t === 'stmt') return b.id ? stmtPreview(b.id) : null;
      if (b.t === 'prose' || b.t === 'proof') {
        const head = b.t === 'proof' ? 'Cited in proof' : 'Cited passage';
        return `<div class="pk">${head}</div><div>${proseHtml(b.tex, refs, cites).slice(0, 1600)}</div>`;
      }
      return null;
    }
    function graphPreview(id: string): string | null {
      const e = byId.get(id);
      if (!e) return null;
      const ups = e.deps.map((d: Dep) => byId.get(d.id)).filter((x): x is Entry => !!x);
      const downs = rev.get(id) || [];
      return `<div class="pv-graphwrap"><div class="pk">Local dependencies</div>${localDepGraph(e, ups, downs)}</div>`;
    }
    function leanTagPreview(id: string): string | null {
      const e = byId.get(id);
      if (!e) return null;
      if (e.lean.length) {
        return e.lean
          .map((l) => `<div class="pk">Lean · ${esc(l.name)}${l.status ? ' · ' + l.status.replace('_', ' ') : ''}</div>${l.code ? `<pre class="lean">${leanHi(l.code)}</pre>` : ''}`)
          .join('');
      }
      if (e.mathlib_name) return `<div class="pk">Mathlib</div><div style="margin-top:4px">${esc(([] as string[]).concat(e.mathlib_name).join(', '))}</div>`;
      return null;
    }

    function show(html: string, x: number, y: number) {
      setPv({ html, x, y });
    }
    function showPinned(html: string, x: number, y: number) {
      pinnedRef.current = false;
      show(html, x, y);
      pinnedRef.current = true;
    }
    function hide() {
      if (!pinnedRef.current) setPv(null);
    }
    function schedHide() {
      window.clearTimeout(hideT.current);
      if (!pinnedRef.current) hideT.current = window.setTimeout(hide, 260);
    }

    function onOver(ev: MouseEvent) {
      if (pinnedRef.current) return;
      const t = ev.target as HTMLElement;
      // a bibliography "Cited in" link — carries `data-loc`, and is also a
      // `.ref`, so it must be matched before the plain `.ref[data-id]` branch
      const locEl = t.closest('.citeloc[data-loc]') as HTMLElement | null;
      const refEl = t.closest('.ref[data-id]') as HTMLElement | null;
      const leanEl = t.closest('.leanref[data-name]') as HTMLElement | null;
      const citeEl = t.closest('.cite[data-cite]') as HTMLElement | null;
      // an overview/chapter-contents status square — a bare colour chip, so
      // the preview is the only thing that says which statement it stands for
      const cellEl = t.closest('.mm[data-id]') as HTMLElement | null;
      // a dependency-graph node — see GraphModal's post-render pass, which
      // tags every `g.node` with `data-nid` (a real entry id, or a
      // synthetic `ch<N>` for a collapsed chapter box — those don't preview)
      const graphNodeEl = t.closest('.node[data-nid]') as HTMLElement | null;
      window.clearTimeout(hideT.current);
      if (locEl?.dataset.loc) {
        const loc = locEl.dataset.loc;
        showT.current = window.setTimeout(() => {
          const h = locPreview(loc);
          if (h) show(h, ev.clientX, ev.clientY);
        }, 110);
      } else if (citeEl) {
        showT.current = window.setTimeout(() => show(citePreview(citeEl.dataset.cite!), ev.clientX, ev.clientY), 110);
      } else if (refEl?.dataset.id) {
        showT.current = window.setTimeout(() => {
          const h = stmtPreview(refEl.dataset.id!);
          if (h) show(h, ev.clientX, ev.clientY);
        }, 110);
      } else if (leanEl?.dataset.name) {
        showT.current = window.setTimeout(() => {
          const h = leanPreview(leanEl.dataset.name!);
          if (h) show(h, ev.clientX, ev.clientY);
        }, 110);
      } else if (cellEl?.dataset.id) {
        const id = cellEl.dataset.id;
        showT.current = window.setTimeout(() => {
          const h = stmtPreview(id);
          if (h) show(h, ev.clientX, ev.clientY);
        }, 110);
      } else if (graphNodeEl?.dataset.nid && !CHAPTER_ID_RE.test(graphNodeEl.dataset.nid)) {
        const nid = graphNodeEl.dataset.nid;
        showT.current = window.setTimeout(() => {
          const h = stmtPreview(nid);
          if (h) show(h, ev.clientX, ev.clientY);
        }, 110);
      }
    }
    function onOut(ev: MouseEvent) {
      if (!pinnedRef.current && (ev.target as HTMLElement).closest('.ref,.leanref,.cite,.mm[data-id],.node[data-nid]')) {
        window.clearTimeout(showT.current);
        schedHide();
      }
    }
    function onDocClick(ev: MouseEvent) {
      const t = ev.target as HTMLElement;

      const gn = t.closest('.gn[data-id]') as HTMLElement | null;
      if (gn?.dataset.id) {
        pinnedRef.current = false;
        setPv(null);
        onNavigate(gn.dataset.id);
        return;
      }

      const popEl = t.closest('.mtag.pop[data-graph], .mtag.pop[data-lean]') as HTMLElement | null;
      if (popEl) {
        const gid = popEl.dataset.graph;
        const lid = popEl.dataset.lean;
        const h = gid ? graphPreview(gid) : lid ? leanTagPreview(lid) : null;
        if (h) showPinned(h, ev.clientX, ev.clientY);
        return;
      }

      if (boxRef.current && !boxRef.current.contains(t) && !t.closest('.ref,.leanref,.cite,.mtag.pop')) {
        pinnedRef.current = false;
        setPv(null);
      }
    }

    document.addEventListener('mouseover', onOver);
    document.addEventListener('mouseout', onOut);
    document.addEventListener('click', onDocClick);
    return () => {
      document.removeEventListener('mouseover', onOver);
      document.removeEventListener('mouseout', onOut);
      document.removeEventListener('click', onDocClick);
    };
  }, [data, root, onNavigate]);

  // The popup's HTML comes from `detex`/`proseHtml`, which leave math as
  // literal `$…$` for KaTeX (see Tex.tsx) — but this box sets its own
  // innerHTML, so nothing had ever typeset it and previews showed raw LaTeX.
  // No dependency array — same React-19 innerHTML-reset caveat as Tex.tsx;
  // typesetMath's O(1) guard makes the per-commit call free when unchanged.
  useEffect(() => {
    if (boxRef.current) typesetMath(boxRef.current, data.macros || {});
  });

  if (!pv) return null;
  const isGraph = pv.html.includes('pv-graphwrap');
  const style: React.CSSProperties = {
    position: 'fixed',
    zIndex: 60,
    left: Math.min(pv.x + 14, window.innerWidth - (isGraph ? Math.min(760, window.innerWidth * 0.94) : 480) - 10),
    top: Math.max(10, Math.min(pv.y + 16, window.innerHeight - 200)),
  };
  return (
    <div
      ref={boxRef}
      id="pv"
      className={`pv${isGraph ? ' pv-graph' : ''}`}
      style={style}
      onMouseEnter={() => window.clearTimeout(hideT.current)}
      onMouseLeave={() => {
        if (!pinnedRef.current) setPv(null);
      }}
      dangerouslySetInnerHTML={{ __html: pv.html }}
    />
  );
}
