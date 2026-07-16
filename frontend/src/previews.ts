import type { Entry, RefEntry } from './types';
import { detex, proseHtml, type CiteNums } from './latex';

const ABBR: Record<string, string> = {
  definition: 'Def', lemma: 'Lem', theorem: 'Thm', proposition: 'Prop',
  corollary: 'Cor', remark: 'Rmk', example: 'Ex', conjecture: 'Conj',
};

/** The small "statement" hover-preview card (tag/number, title, prose,
 * truncated) — shared by the document view's `.ref`/`.leanref` hover
 * (`HoverPreview`) and the dependency graph's node hover, exactly as the
 * original's `stmtPv` fed both. */
export function stmtPreviewHtml(e: Entry, refs: Record<string, RefEntry>, cites: CiteNums = {}): string {
  const r = refs[e.label || ''];
  return `<div class="pk">${r?.abbr || ABBR[e.kind] || e.kind} ${r?.num || ''}</div><div class="pt">${detex(e.title, refs, cites)}</div><div>${proseHtml(e.body, refs, cites).slice(0, 1200)}</div>`;
}
