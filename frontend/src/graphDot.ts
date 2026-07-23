import type { Chapter, Entry, ProjectData } from './types';
import { plainTex } from './latex';
import { GRAPH } from './palette';

// _DEF_KINDS / _DONE mirror hgraph.layout — keep in lockstep. The colours live
// in palette.ts (mirrored by hgraph/layout.py for the server-side render).
const GBORDER = GRAPH.border;
const GFILL = GRAPH.fill;
const DEF_KINDS = new Set(['definition', 'example', 'remark', 'notation', 'convention']);
const DONE = new Set(['lean_ok', 'mathlib_ok']);
const LVL: Record<string, number> = { coarse: 0, medium: 1, fine: 2 };

export function isDefKind(kind: string): boolean {
  return DEF_KINDS.has(kind);
}

interface GNode {
  id: string;
  e: Entry;
  i: number;
  ch: number;
  lvl: number;
  stmt: 'formalized' | 'ready' | 'blocked';
  proof: 'done' | 'local' | 'incomplete' | 'ready' | 'notready';
}

export interface ChapterStat {
  key: number;
  label: string;
  count: number;
  done: number;
}

export interface GraphModel {
  nodes: GNode[];
  idx: Map<string, number>;
  edges: [number, number, string][]; // [source, target, type] — source uses target
  chapters: ChapterStat[];
}

function gvEsc(s: string): string {
  return String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function dotLabel(title: string): string {
  const words = plainTex(title || '').split(/\s+/);
  const lines: string[] = [];
  let cur = '';
  const MAX = 20;
  for (const w of words) {
    const c = cur ? cur + ' ' + w : w;
    if (c.length <= MAX || !cur) cur = c;
    else {
      lines.push(cur);
      cur = w;
      if (lines.length >= 2) break;
    }
  }
  if (cur && lines.length < 3) lines.push(cur);
  if (lines.length >= 3 && lines[2].length > MAX) lines[2] = lines[2].slice(0, MAX - 1) + '…';
  return lines.map(gvEsc).join('\\n');
}

/** Progress-ramp colour, `GRAPH.fill.notready` -> `GRAPH.fill.done` — unused
 * for now (chapter boxes use the fixed purple "this is a chapter" colour,
 * matching the original's `gmDotMixed`/`_dot_overview` exactly) but kept in
 * lockstep with `hgraph.layout._gv_green`, which does use it. */
function gvGreen(pct: number): string {
  const t = Math.max(0, Math.min(1, pct / 100));
  const lerp = (a: number, b: number) => Math.round(a + (b - a) * t).toString(16).padStart(2, '0');
  return '#' + [[0xec, 0x66], [0xf3, 0xbb], [0xec, 0x6a]].map(([a, b]) => lerp(a, b)).join('');
}
void gvGreen;

/** Builds the node/edge/chapter model once per `data` fetch — mirrors the
 * original's `gmBuild` + `gmChapters` + `gmStatuses` (and `hgraph.layout._Model`,
 * its build-time Python twin) so the live DOT below matches byte-for-byte. */
export function buildGraphModel(data: ProjectData): GraphModel {
  const entries = data.entries;
  const loc = data.loc || {};
  const idx = new Map<string, number>();
  entries.forEach((e, i) => idx.set(e.id, i));

  const edges: [number, number, string][] = [];
  const seen = new Set<string>();
  for (const e of entries) {
    const s = idx.get(e.id)!;
    for (const d of e.deps) {
      const t = idx.get(d.id);
      if (t == null || t === s) continue;
      const k = s + '_' + t;
      if (seen.has(k)) continue;
      seen.add(k);
      edges.push([s, t, d.type || 'uses']);
    }
  }

  // chapters, in first-appearance order (by `loc`, falling back to the raw `chapter` field)
  const chapterOrder: (number | string)[] = [];
  const seenCh = new Map<number | string, number>();
  const chOf: number[] = new Array(entries.length);
  entries.forEach((e, i) => {
    const k = loc[e.id] ?? e.chapter ?? '·';
    if (!seenCh.has(k)) {
      seenCh.set(k, chapterOrder.length);
      chapterOrder.push(k);
    }
    chOf[i] = seenCh.get(k)!;
  });
  const chapters: Chapter[] = data.chapters || [];
  // "Chapter 3 · Curvature" — the word is worth the width: a bare "3 Curvature"
  // reads as part of the title. A node whose chapter is a raw string (not an
  // index into `chapters`) has no number and stays as-is.
  const chLabel = (k: number | string): string => {
    if (typeof k === 'number' && chapters[k]) {
      const title = plainTex(chapters[k].title);
      const num = chapters[k].num;
      const word = chapters[k].appendix ? 'Appendix' : 'Chapter';
      return num ? `${word} ${num} · ${title}` : title;
    }
    return plainTex(String(k)).slice(0, 30);
  };

  // dependency adjacency (i -> what it needs), used for closure + statement/proof status
  const depsAdj: number[][] = entries.map(() => []);
  edges.forEach(([s, t]) => depsAdj[s].push(t));
  const F = entries.map((e) => DONE.has(e.lean_status));

  // iterative (cycle-safe) closure: closed iff locally done AND every dep closed
  const closed: boolean[] = new Array(entries.length).fill(false);
  {
    const memo = new Array<boolean | undefined>(entries.length);
    const onstack = new Array(entries.length).fill(false);
    for (let root = 0; root < entries.length; root++) {
      if (memo[root] !== undefined) continue;
      const stack: [number, number][] = [[root, 0]];
      onstack[root] = true;
      while (stack.length) {
        const [i, ci0] = stack[stack.length - 1];
        if (!F[i]) {
          memo[i] = false;
          onstack[i] = false;
          stack.pop();
          continue;
        }
        const D = depsAdj[i];
        let ci = ci0;
        let advanced = false;
        while (ci < D.length) {
          const t = D[ci];
          ci++;
          if (memo[t] === undefined && !onstack[t]) {
            stack[stack.length - 1] = [i, ci];
            stack.push([t, 0]);
            onstack[t] = true;
            advanced = true;
            break;
          }
        }
        if (advanced) continue;
        let r = true;
        for (const t of D) {
          const depClosed = memo[t] !== undefined ? memo[t]! : F[t];
          if (!depClosed) {
            r = false;
            break;
          }
        }
        memo[i] = r;
        onstack[i] = false;
        stack.pop();
      }
    }
    for (let i = 0; i < entries.length; i++) closed[i] = !!memo[i];
  }

  const nodes: GNode[] = entries.map((e, i) => {
    const D = depsAdj[i];
    const ls = e.lean_status;
    const allLean = D.every((t) => entries[t].lean_status !== 'empty');
    const allF = D.every((t) => F[t]);
    const stmt: GNode['stmt'] = ls !== 'empty' ? 'formalized' : !D.length || allLean ? 'ready' : 'blocked';
    const proof: GNode['proof'] = closed[i]
      ? 'done'
      : F[i]
        ? 'local'
        : ls === 'sorry'
          ? 'incomplete'
          : ls === 'empty' && (!D.length || allF)
            ? 'ready'
            : 'notready';
    return { id: e.id, e, i, ch: chOf[i], lvl: e.level != null && LVL[e.level] != null ? LVL[e.level] : 2, stmt, proof };
  });

  const chapterStats: ChapterStat[] = chapterOrder.map((k, ch) => {
    const count = nodes.filter((n) => n.ch === ch).length;
    const done = nodes.filter((n) => n.ch === ch && closed[n.i]).length;
    return { key: ch, label: chLabel(k), count, done };
  });

  return { nodes, idx, edges, chapters: chapterStats };
}

function nodeStyle(n: GNode): { b: string; f: string } {
  return { b: GBORDER[n.stmt] || GRAPH.defaultBorder, f: GFILL[n.proof] || GRAPH.defaultFill };
}

/** The synthetic id for a collapsed chapter's aggregate box (see `dotMixed`). */
export function chapterNodeId(ch: number): string {
  return 'ch' + ch;
}
export const CHAPTER_ID_RE = /^ch(\d+)$/;

/** Where an edge endpoint should resolve to for the *current* expand/level
 * state: its own id if the node is visible (its chapter is expanded and its
 * level passes the filter), its chapter's aggregate box id if collapsed, or
 * `null` if it's hidden entirely (expanded but filtered out by level) — the
 * edge is then dropped. Mirrors the original's `gmDispId`. */
function dispId(n: GNode, expanded: ReadonlySet<number>, lvlMax: number): string | null {
  if (expanded.has(n.ch)) return n.lvl <= lvlMax ? n.id : null;
  return chapterNodeId(n.ch);
}

/** The one graph: every chapter not in `expanded` is a single purple
 * aggregate box (`ch<N>`, click -> expand); every chapter IN `expanded` is a
 * real `subgraph cluster_<N>` containing its individual nodes, filtered by
 * `lvlMax`. Edges always resolve to whatever's currently visible. Ported
 * from the original's `gmDotMixed` — regenerate this (and re-render via
 * Graphviz) on every expand/collapse/level change, never hide/show a stale
 * layout. */
export function dotMixed(model: GraphModel, expanded: ReadonlySet<number>, lvlMax: number): string {
  const byCh = new Map<number, GNode[]>();
  model.nodes.forEach((n) => {
    if (!byCh.has(n.ch)) byCh.set(n.ch, []);
    byCh.get(n.ch)!.push(n);
  });

  let s = 'strict digraph "" {\n';
  s += '  rankdir=TB;bgcolor="transparent";pack=true;packmode="clust";splines=true;nodesep=0.4;ranksep=0.6;\n';
  s += '  node [shape=box,style="rounded,filled",fontname="Helvetica",fontsize=11,margin="0.11,0.05",penwidth=1.8];\n';
  s += `  edge [color="${GRAPH.edge}",arrowhead=vee,arrowsize=0.8,penwidth=1];\n`;
  s += '  graph [fontname="Helvetica",fontsize=13,labeljust="l"];\n';

  model.chapters.forEach((stat, ch) => {
    if (!stat.count) return;
    if (expanded.has(ch)) {
      s += `  subgraph cluster_${ch} {\n    label="${gvEsc(stat.label + '  (click background to close)')}";style="rounded,filled";fillcolor="${GRAPH.expandedFill}";color="${GRAPH.clusterBorder}";penwidth=2.4;fontcolor="${GRAPH.expandedText}";fontsize=12.5;\n`;
      (byCh.get(ch) || [])
        .filter((n) => n.lvl <= lvlMax)
        .forEach((n) => {
          const st = nodeStyle(n);
          const def = isDefKind(n.e.kind);
          s += `    "${n.id}" [shape=${def ? 'box' : 'ellipse'},style=${def ? '"rounded,filled"' : '"filled"'},fillcolor="${st.f}",color="${st.b}",fontcolor="${GRAPH.nodeText}",label="${dotLabel(n.e.title || n.e.label || n.e.id)}"];\n`;
        });
      s += '  }\n';
    } else {
      const pct = Math.round((100 * stat.done) / stat.count);
      s += `  "ch${ch}" [label="${gvEsc(stat.label)}\\n${stat.count} statements · ${pct}%",fillcolor="${GRAPH.clusterFill}",color="${GRAPH.clusterBorder}",penwidth=2.6,fontcolor="${GRAPH.clusterText}",tooltip="${gvEsc(stat.label)} — click to expand"];\n`;
    }
  });

  const seenEdge = new Set<string>();
  model.edges.forEach(([si, ti, ty]) => {
    const sN = model.nodes[si];
    const tN = model.nodes[ti];
    const sId = dispId(sN, expanded, lvlMax);
    const tId = dispId(tN, expanded, lvlMax);
    if (sId == null || tId == null || sId === tId) return;
    const key = `${sId} ${tId} ${ty}`;
    if (seenEdge.has(key)) return;
    seenEdge.add(key);
    s += `  "${tId}" -> "${sId}"${ty === 'uses' ? ' [style=dashed]' : ''};\n`;
  });

  return s + '}\n';
}
