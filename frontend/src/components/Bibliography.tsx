import { useEffect, useRef } from 'react';
import type { BibEntry, Entry, RefEntry } from '../types';
import { detex, esc } from '../latex';
import { typesetMath } from '../typeset';

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
 * "cited from" back-reference list built by scanning entry bodies for
 * `\cite{...}` — ported from the original's `renderBiblio`/`fmtBib` and the
 * `CITES` reverse index built in `index()`. */
export function Bibliography({
  bib,
  entries,
  refs,
  onSelect,
  flashKey,
}: {
  bib: BibEntry[];
  entries: Entry[];
  refs: Record<string, RefEntry>;
  onSelect: (id: string) => void;
  flashKey?: string | null;
}) {
  const cites = new Map<string, string[]>();
  const cre = /\\cite[tp]?\*?\{([^{}]*)\}/g;
  for (const e of entries) {
    cre.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = cre.exec(e.body || ''))) {
      for (let k of m[1].split(',')) {
        k = k.trim();
        if (!k) continue;
        if (!cites.has(k)) cites.set(k, []);
        cites.get(k)!.push(e.id);
      }
    }
  }

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
        const cb = cites.get(b.key) || [];
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
              Cited from ({cb.length})
              {cb.length > 0 ? ': ' : ''}
              {cb
                .map((id) => {
                  const e = entries.find((x) => x.id === id);
                  if (!e) return null;
                  const r = (e.label && refs[e.label]) || null;
                  const label = r?.abbr ? `${r.abbr} ${r.num}` : (e.label || id).replace(/^[a-z]+:/, '');
                  return (
                    // `data-id` is what HoverPreview delegates on — without it
                    // these read as cross-reference links but never preview
                    <a className="ref" key={id} data-id={id} onClick={() => onSelect(id)}>
                      {label}
                    </a>
                  );
                })
                .filter(Boolean)
                .reduce((acc: React.ReactNode[], el, idx) => (idx === 0 ? [el] : [...acc, ', ', el]), [])}
            </div>
          </div>
        );
      })}
    </div>
  );
}
