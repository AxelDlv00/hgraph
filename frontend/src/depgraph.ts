import type { Entry } from './types';
import { plainTex, esc } from './latex';
import { statusNodeStyle } from './palette';

function entryStyle(e: Entry): { b: string; f: string } {
  return statusNodeStyle(e.lean_status);
}

function defKind(k: string): boolean {
  return k === 'definition' || k === 'example' || k === 'remark' || k === 'notation' || k === 'convention';
}

function wrapTitle(t: string, maxc: number, maxl: number): string[] {
  const full = plainTex(t || '').trim();
  if (!full) return [''];
  const words = full.split(/\s+/);
  const out: string[] = [];
  let cur = '';
  let i = 0;
  while (i < words.length) {
    const w = words[i];
    const c = cur ? cur + ' ' + w : w;
    if (c.length <= maxc || !cur) {
      cur = c;
      i++;
    } else {
      if (out.length === maxl - 1) break;
      out.push(cur);
      cur = '';
    }
  }
  if (cur && out.length < maxl) out.push(cur);
  if (i < words.length) {
    let last = out.length ? out[out.length - 1] : '';
    while (last.length > maxc - 1) last = last.slice(0, -1);
    out[out.length ? out.length - 1 : 0] = last.replace(/[ ,;:]+$/, '') + '…';
  }
  return out;
}

function dlabel(nd: Entry): string {
  const t = plainTex(nd.title || '');
  if (t) return t;
  const l = (nd.label || '').replace(/^[a-z]+:/, '').replace(/[-_]/g, ' ').trim();
  return l || nd.kind || 'node';
}

/** The "local dependencies" mini SVG diagram — three rows (uses ↑ / this entry /
 * used-by ↓) with curved arrows — ported from the original's `depGraph(e)`. Used
 * both in the click-pinned "uses N · used by N" popup (see HoverPreview) and the
 * dependency-graph tab's node detail panel ("Dependencies" section). */
export function localDepGraph(e: Entry, allUps: Entry[], allDowns: Entry[], hint = false): string {
  if (!allUps.length && !allDowns.length) return `<div class="ro">No dependency edges.</div>`;
  const CAP = 5,
    MAXL = 3;
  const u = allUps.slice(0, CAP),
    dn = allDowns.slice(0, CAP);
  const rows: [string, Entry[]][] = [
    ['uses ↑', u],
    ['', [e]],
    ['↓ used by', dn],
  ];
  const lab = new Map<Entry, string[]>();
  [...u, e, ...dn].forEach((nd) => lab.set(nd, wrapTitle(dlabel(nd), 22, MAXL)));
  const maxLines = Math.max(1, ...[...lab.values()].map((l) => l.length));
  const per = Math.max(u.length, dn.length, 1);
  const BW = 156,
    BH = 14 + maxLines * 13;
  const W = Math.max(516, per * (BW + 18) + 84);
  const rowH = BH + 30,
    pad = 16,
    cx = W / 2;
  const H = pad * 2 + rowH * 3;
  const yOf = (i: number) => pad + rowH * i + rowH / 2;
  // keyed by row+id, not by Entry: with a mutual (cyclic) dependency the same
  // entry sits in both the "uses" and "used by" rows, and an Entry-keyed map
  // would overwrite the up-row position with the down-row one, drawing the
  // "uses" arrow from the wrong row
  const pos = new Map<string, { x: number; y: number }>();
  let boxes = '',
    lines = '';
  rows.forEach(([, list], i) => {
    const n = list.length;
    list.forEach((nd, j) => {
      const x = 80 + ((W - 92) / (n + 1)) * (j + 1);
      const y = yOf(i);
      pos.set(i + ':' + nd.id, { x, y });
      const me = i === 1;
      const tl = lab.get(nd)!;
      const st = entryStyle(nd),
        def = defKind(nd.kind),
        w = BW;
      const shape = def
        ? `<rect width="${w}" height="${BH}" rx="7" fill="${me ? '#eef1ff' : st.f}" stroke="${me ? '#4f46e5' : st.b}" stroke-width="${me ? 2.4 : 2}"/>`
        : `<ellipse cx="${w / 2}" cy="${BH / 2}" rx="${w / 2}" ry="${BH / 2}" fill="${me ? '#eef1ff' : st.f}" stroke="${me ? '#4f46e5' : st.b}" stroke-width="${me ? 2.4 : 2}"/>`;
      const y0 = BH / 2 - (tl.length - 1) * 6.5 + 3.5;
      const txt = tl.map((ln, k) => `<tspan x="${w / 2}" ${k ? 'dy="13"' : ''}>${esc(ln)}</tspan>`).join('');
      boxes += `<g class="gn" ${me ? '' : `data-id="${nd.id}"`} transform="translate(${x - w / 2},${y - BH / 2})">${shape}<text x="${w / 2}" y="${y0}" text-anchor="middle" fill="#1c2024" font-size="11">${txt}</text></g>`;
    });
  });
  const curve = (x1: number, y1: number, x2: number, y2: number) => {
    const my = (y1 + y2) / 2;
    return `<path d="M${x1} ${y1} C${x1} ${my.toFixed(1)} ${x2} ${my.toFixed(1)} ${x2} ${y2}" fill="none" stroke="#c1c6d0" stroke-width="1.4" marker-end="url(#ah)"/>`;
  };
  u.forEach((nd) => {
    const p = pos.get('0:' + nd.id)!;
    lines += curve(p.x, p.y + BH / 2, cx, yOf(1) - BH / 2);
  });
  dn.forEach((nd) => {
    const p = pos.get('2:' + nd.id)!;
    lines += curve(cx, yOf(1) + BH / 2, p.x, p.y - BH / 2);
  });
  const rlab = rows.map(([label], i) => (label ? `<text x="8" y="${yOf(i) + 4}" fill="#6b7280" font-size="10">${label}</text>` : '')).join('');
  const more =
    (allUps.length > CAP ? `<div class="ro">+${allUps.length - CAP} more used ↑. </div>` : '') +
    (allDowns.length > CAP ? `<div class="ro">+${allDowns.length - CAP} more use this.</div>` : '');
  const hintHtml = hint ? `<div class="ro" style="background:none;padding:4px 2px 0">click a node to open it</div>` : '';
  return `<div class="gwrap"><svg class="graph" viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet" style="height:auto;max-height:480px;display:block"><defs><marker id="ah" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 z" fill="#c1c6d0"/></marker></defs>${rlab}${lines}${boxes}</svg></div>${more}${hintHtml}`;
}
