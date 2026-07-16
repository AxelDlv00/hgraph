import type { Chapter, StmtBlock } from './types';

export interface TreeSubsection {
  num: string;
  title: string;
  stmts: StmtBlock[];
}
export interface TreeSection {
  num: string;
  title: string;
  stmts: StmtBlock[];
  subs: TreeSubsection[];
}

/** Chapter -> [section, ...], each carrying its own statements plus any
 * subsections (each with their own statements) — ported from the original's
 * `chapterTree(ch)`. A section with no `\subsection` heading yet (or a
 * chapter with no `\section` heading at all) still gets one anonymous
 * section so its statements aren't dropped. Used by both the TOC's chapter
 * tree and the Overview drill-down page. */
export function chapterTree(ch: Chapter): TreeSection[] {
  const secs: TreeSection[] = [];
  let sec: TreeSection | null = null;
  const own = (): TreeSection => {
    if (!sec) {
      sec = { num: '', title: '', stmts: [], subs: [] };
      secs.push(sec);
    }
    return sec;
  };
  for (const b of ch.blocks) {
    if (b.t === 'head' && b.level === 2 && b.num) {
      sec = { num: b.num, title: b.title, stmts: [], subs: [] };
      secs.push(sec);
    } else if (b.t === 'head' && b.level === 3 && b.num) {
      own().subs.push({ num: b.num, title: b.title, stmts: [] });
    } else if (b.t === 'stmt') {
      const s = own();
      (s.subs.length ? s.subs[s.subs.length - 1] : s).stmts.push(b);
    }
  }
  return secs;
}
