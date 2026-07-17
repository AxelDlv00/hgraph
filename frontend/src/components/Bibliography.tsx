import { useEffect, useMemo, useRef } from 'react';
import type { BibEntry, Chapter } from '../types';
import { detex, esc } from '../latex';
import { typesetMath } from '../typeset';
import { buildCiteIndex } from '../citeindex';

function bibAuthors(a: string | null): string {
  if (!a) return '';
  return a
    .split(/\s+and\s+/)
    .map((p) => {
      p = p.trim();
      if (p.includes(',')) {
        const i = p.indexOf(',');
        return (p.slice(i + 1).trim() + ' ' + p.slice(0, i).trim()).trim();
      }
      return p;
    })
    .join(', ');
}

function fmtBib(b: BibEntry): string {
  const au = bibAuthors(b.author);
  let s = '';
  if (au) s += `<span style="font-weight:600">${esc(au)}</span>`;
  if (b.year) s += ` (${esc(b.year)})`;
  s += au || b.year ? '. ' : '';
  s += `“${detex(b.title || b.key)}”.`;
  if (b.journal || b.booktitle) s += ` <em>${detex(b.journal || b.booktitle || '')}</em>.`;
  const vp: string[] = [];
  if (b.volume) vp.push(b.number ? `${esc(b.volume)}(${esc(b.number)})` : esc(b.volume));
  if (b.pages) vp.push('pp. ' + esc(b.pages).replace(/--/g, '–'));
  if (vp.length) s += ' ' + vp.join(', ') + '.';
  if (b.publisher && !(b.journal || b.booktitle)) s += ` ${detex(b.publisher)}.`;
  return s;
}

/** The "Blueprint bibliography" tab — every `.bib` entry, formatted, with a
 * "Cited in" list of every place in the document that `\cite`s it. Unlike the
 * old reverse index (which scanned only statement bodies), this uses
 * `buildCiteIndex` over the whole chapter tree, so citations that live in the
 * prose or proofs *between* the lemmas are listed too. Each location links to
 * the block; hovering it previews the citing passage (see HoverPreview's
 * `.citeloc` handling). */
export function Bibliography({
  bib,
  chapters,
  onGotoLoc,
  flashKey,
}: {
  bib: BibEntry[];
  chapters: Chapter[];
  onGotoLoc: (chapterIndex: number, blockIndex: number, anchor: string) => void;
  flashKey?: string | null;
}) {
  const cites = useMemo(() => buildCiteIndex(chapters), [chapters]);

  const ref = useRef<HTMLDivElement | null>(null);
  // a bib title/journal can itself contain math ($...$) left un-rendered by
  // `detex` (see Tex.tsx) — one KaTeX pass over the whole list, re-checked
  // after every commit (no deps — same React-19 innerHTML-reset caveat as
  // Tex.tsx; typesetMath's guard makes the call O(1) when nothing changed).
  useEffect(() => {
    if (ref.current) typesetMath(ref.current);
  });

  return (
    <div className="doc" ref={ref}>
      <h2 className="ch">
        Blueprint bibliography <span style={{ color: 'var(--muted)', fontWeight: 400, fontSize: 18 }}>({bib.length})</span>
      </h2>
      {bib.length === 0 && (
        <div className="ro">
          No bibliography found. Drop a <code>.bib</code> next to the blueprint and it appears here; <code>\cite{'{…}'}</code> in the
          text will link to it.
        </div>
      )}
      {bib.map((b, i) => {
        const locs = cites.get(b.key) || [];
        return (
          <div className={`bibitem${flashKey === b.key ? ' flash' : ''}`} key={b.key} data-key={b.key}>
            <div className="bi-t">
              <span className="bi-n">[{i + 1}]</span> <span dangerouslySetInnerHTML={{ __html: fmtBib(b) }} />
              {b.url && (
                <>
                  {' '}
                  <a href={b.url} target="_blank" rel="noopener noreferrer" title="open">
                    ↗
                  </a>
                </>
              )}
            </div>
            <div className="bi-c">
              Cited in ({locs.length})
              {locs.length > 0 ? ': ' : ''}
              {locs.map((loc, j) => (
                <span key={`${loc.anchor}-${j}`}>
                  {j > 0 && ', '}
                  {/* `.citeloc[data-loc]` is what HoverPreview delegates on to
                      preview the citing passage; the click jumps to it */}
                  <a
                    className="ref citeloc"
                    data-loc={`${loc.chapterIndex}:${loc.blockIndex}`}
                    onClick={() => onGotoLoc(loc.chapterIndex, loc.blockIndex, loc.anchor)}
                  >
                    {loc.label}
                  </a>
                </span>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
