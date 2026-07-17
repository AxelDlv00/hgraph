// Reverse citation index: for every `.bib` key, *where in the document it is
// cited* — not just the statements whose bodies `\cite` it (the old
// Bibliography scanned only those), but the prose and proof blocks between
// them, which is where most citations actually live. Shared by the
// Bibliography tab (renders one clickable location per citing block) and
// HoverPreview (previews the citing passage on hover).

import type { Chapter } from './types';

export interface CiteLoc {
  /** which chapter/block cites the key — enough to switch to it and scroll */
  chapterIndex: number;
  blockIndex: number;
  /** the element id the ChapterView gives this block (see ChapterView's blockAnchor) */
  anchor: string;
  /** short label for the link, e.g. "Lem 2.2" or "§2.1" */
  label: string;
  kind: 'prose' | 'proof' | 'stmt';
}

// keep in step with latex.ts's \cite rule: every natbib variant
// (\citet, \citealp, \citeauthor, …) plus an optional [page] argument
const CITE_RE = /\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])?\{([^{}]*)\}/g;

/** The distinct bib keys `\cite`d anywhere in a chunk of TeX. */
function citeKeys(tex: string): Set<string> {
  const keys = new Set<string>();
  CITE_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = CITE_RE.exec(tex))) {
    for (let k of m[1].split(',')) {
      k = k.trim();
      if (k) keys.add(k);
    }
  }
  return keys;
}

/** bib key -> the ordered, de-duplicated list of blocks that cite it (document
 * order). A key cited several times inside one block collapses to a single
 * location — one clickable place, not one per `\cite`. */
export function buildCiteIndex(chapters: Chapter[]): Map<string, CiteLoc[]> {
  const out = new Map<string, CiteLoc[]>();
  chapters.forEach((ch, ci) => {
    // the nearest enclosing section number, so a prose/proof citation reads as
    // "§2.1"; before the first \section it falls back to the chapter number
    let sectionNum = ch.num || '';
    ch.blocks.forEach((b, bi) => {
      if (b.t === 'head') {
        if (b.num) sectionNum = b.num;
        return;
      }
      let tex = '';
      let anchor = '';
      let label = '';
      let kind: CiteLoc['kind'];
      if (b.t === 'prose') {
        tex = b.tex;
        anchor = `blk-${bi}`;
        kind = 'prose';
        label = sectionNum ? `§${sectionNum}` : '¶';
      } else if (b.t === 'proof') {
        tex = b.tex;
        anchor = `blk-${bi}`;
        kind = 'proof';
        label = sectionNum ? `§${sectionNum} proof` : 'proof';
      } else if (b.t === 'stmt') {
        tex = b.body;
        anchor = `stmt-${b.id}`;
        kind = 'stmt';
        label = `${b.abbr || ''} ${b.num || ''}`.trim() || (sectionNum ? `§${sectionNum}` : 'statement');
      } else {
        return;
      }
      for (const k of citeKeys(tex)) {
        if (!out.has(k)) out.set(k, []);
        out.get(k)!.push({ chapterIndex: ci, blockIndex: bi, anchor, label, kind });
      }
    });
  });
  return out;
}
