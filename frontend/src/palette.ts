// The one place status colors are defined.
//
// Before this module the same four-colour map was written out by hand in five
// places (StatusBadge, ChapterView, Overview, Summary, depgraph) and had already
// drifted — `sorry` was #d11a2a in three of them and #C2410C in a fourth,
// `empty` was #9aa2ad in two and #c7ccd4 in another. Import from here instead:
// the values are the original design's, but there is now exactly one copy of
// each, so a swatch and the thing it describes cannot fall out of step.
//
// The graph colours below are mirrored by `hgraph/layout.py` (_GBORDER /
// _GFILL / _CLUSTER / ...) for the server-side Graphviz render — keep the two
// in lockstep; `npm run build` does not check this for you.

/** The four Lean states a statement can be in, as shown to the reader. */
export type Status = 'mathlib_ok' | 'lean_ok' | 'sorry' | 'empty';

export interface StatusStyle {
  /** foreground / solid swatch — readable on `bg` and on white */
  fg: string;
  /** tinted background for pills and badges */
  bg: string;
  label: string;
}

export const STATUS: Record<Status, StatusStyle> = {
  mathlib_ok: { fg: '#0B5FD0', bg: '#E3EEFB', label: 'mathlib' },
  lean_ok: { fg: '#137333', bg: '#E3F3E8', label: 'lean ok' },
  sorry: { fg: '#C2410C', bg: '#FBE8E6', label: 'sorry' },
  empty: { fg: '#6B7280', bg: '#EEF0F3', label: 'no lean' },
};

export function statusStyle(s?: string | null): StatusStyle {
  return STATUS[(s || 'empty') as Status] || STATUS.empty;
}

/** Solid swatch/segment colour for a status — legends, segmented bars, squares. */
export function statusColor(s?: string | null): string {
  return statusStyle(s).fg;
}

/** A graph node coloured by its Lean status (the local dependency mini-graph),
 * so a node reads as the same state as that statement's badge: tinted fill,
 * deep border. Distinct from `GRAPH` below, which buckets by *proof* state. */
export function statusNodeStyle(s?: string | null): { b: string; f: string } {
  const st = statusStyle(s);
  return { b: st.fg, f: st.bg };
}

// ---- dependency-graph nodes --------------------------------------------- //

export const GRAPH = {
  /** statement status -> node border */
  border: {
    formalized: '#2e7d32',
    ready: '#1565c0',
    blocked: '#b0bec5',
  } as Record<string, string>,
  /** proof status -> node fill. `local` (this statement's Lean checks) and
   * `done` (its dependencies check too) are a light/strong green pair. */
  fill: {
    done: '#66bb6a',
    local: '#c8e6c9',
    incomplete: '#ffcc80',
    ready: '#bbdefb',
    notready: '#eef1f4',
  } as Record<string, string>,
  /** fallbacks, used when a node's stmt/proof bucket isn't one of the above */
  defaultBorder: '#b0bec5',
  defaultFill: '#eef1f4',
  /** purple = "this is a chapter": the collapsed aggregate box... */
  clusterFill: '#ede9fe',
  clusterBorder: '#7c3aed',
  clusterText: '#3b0a91',
  /** ...and the same chapter once expanded into a cluster of its statements
   * (a paler wash, so the nodes inside stay the focus) */
  expandedFill: '#f3effc',
  expandedText: '#5b21b6',
  /** node label ink, and edges */
  nodeText: '#1c2024',
  edge: '#8a93a0',
} as const;
