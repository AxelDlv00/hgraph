// Faithful port of the original dashboard's text-mode LaTeX -> HTML pipeline
// (detex/detexRest/inlineMacros/mathEnvs) — math ($…$, \(…\), \[…\], $$…$$)
// is left untouched for KaTeX; everything else (text macros, lists, accents,
// environments) becomes real HTML. Only the `xref`/`\cite` link-building
// changed shape (data-* attributes -> onClick handlers wired up by the
// caller after innerHTML is set — see ChapterView.tsx).

export function esc(s?: string | null): string {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export interface RefEntry {
  num: string;
  /** the graph node id, for a statement — the only ref kind with one */
  id: string | null;
  abbr: string;
  kind?: 'stmt' | 'sec' | 'chap' | 'eq';
  /** chapter index, so a ref into another chapter can switch to it */
  ch?: number;
  /** element id to scroll to within that chapter ("" = the chapter's top) */
  anchor?: string;
}

/** bib key -> its 1-based position in the bibliography, so `\cite{foo}` can
 * render as "[2]" the way LaTeX numbers it rather than as the raw key. Build it
 * with `citeNums(data.bib)`; an unknown key falls back to showing the key. */
export type CiteNums = Record<string, number>;

export function citeNums(bib?: { key: string }[] | null): CiteNums {
  const out: CiteNums = {};
  (bib || []).forEach((b, i) => (out[b.key] = i + 1));
  return out;
}

/** `\ref{a,b}` / `\cref{a,b}` / `\eqref{a}` -> numbered links (or a plain xref
 * span if unresolved). Statements link by node id; chapters, sections and
 * equations have no node, so they link by "<chapter index>:<element id>" and
 * the click handler scrolls there instead (see ProjectView's navigate).
 * `bare` is `\eqref`'s form: the number alone, parenthesised as LaTeX does. */
export function xref(labels: string, refs: Record<string, RefEntry>, bare = false): string {
  return labels
    .split(',')
    .map((l) => {
      l = l.trim();
      const r = refs[l];
      if (!r) return `<span class="xref">${esc(l.replace(/^[a-z]+:/, ''))}</span>`;
      const num = r.kind === 'eq' ? `(${r.num})` : r.num;
      const text = bare ? num : `${esc(r.abbr)}&nbsp;${num}`;
      if (r.id) return `<a class="ref" data-id="${r.id}">${text}</a>`;
      if (r.ch !== undefined && r.anchor !== undefined)
        return `<a class="ref" data-loc="${r.ch}:${esc(r.anchor)}">${text}</a>`;
      return `<span class="ref" style="color:var(--muted);cursor:default">${text}</span>`;
    })
    .join(', ');
}

/** A statement in *another* project, resolved to its number/abbr at build time
 *  — the browser can't look it up, because the target's `refs` live in a sibling
 *  project's data.json that this view never loads. See `\citeext`. */
export interface ExtRefTarget {
  num: string;
  abbr: string;
}
export interface ExtProject {
  root: string;
  name: string;
  /** only the labels this project actually cites: label -> {num, abbr} */
  refs: Record<string, ExtRefTarget>;
}

// `extrefs` is project-global (like the KaTeX macros), so rather than thread it
// through every component that renders prose we keep it in a module var the
// `\citeext` rule reads, set once per project load (see ProjectView).
let _extRefs: Record<string, ExtProject> = {};
export function setExtRefs(m?: Record<string, ExtProject> | null): void {
  _extRefs = m || {};
}

/** `\citeext{Handle}{label}` (and bare `\citeext{Handle}`) -> a cross-project
 *  link rendered like a normal xref ("Thm 1.2 (Project name)"). Navigation is
 *  the existing `#/<root>#<label>` hash contract, which App resolves on load, so
 *  a plain `href` is all that is needed. An unknown handle (e.g. a solo
 *  `hgraph serve` with no siblings) degrades to muted text. */
export function extref(handle: string, label: string | null): string {
  const proj = _extRefs[handle];
  if (!proj) {
    const shown = label ? `${esc(label.replace(/^[a-z]+:/, ''))} (${esc(handle)})` : `(${esc(handle)})`;
    return `<span class="extref extref-dead">${shown}</span>`;
  }
  if (!label) return `<a class="extref" href="#/${proj.root}">(${esc(proj.name)})</a>`;
  const t = proj.refs[label];
  const text = t ? `${esc(t.abbr)}&nbsp;${esc(t.num)}` : esc(label.replace(/^[a-z]+:/, ''));
  return `<a class="extref" href="#/${proj.root}#${encodeURIComponent(label)}">${text} (${esc(proj.name)})</a>`;
}

// Resolve text-formatting macros innermost-first so nested braces render, e.g.
// \textit{Source: \texttt{Foo.Bar} in \texttt{A/B.lean}, L44--L440} -> all levels.
function imRules(refs: Record<string, RefEntry>, cites: CiteNums): [RegExp, string | ((...a: string[]) => string)][] {
  return [
    [/\\paragraph\{([^{}]*)\}/g, '<b>$1.</b> '],
    [/\\(?:sub)*section\*?\{([^{}]*)\}/g, '<strong>$1</strong> '],
    [/\\(?:emph|textit|textsl|textsc)\{([^{}]*)\}/g, '<em>$1</em>'],
    [/\\textbf\{([^{}]*)\}/g, '<strong class="tex-bold">$1</strong>'],
    [/\{\\(?:bfseries|bf)(?![a-zA-Z])\s*([^{}]*)\}/g, '<strong class="tex-bold">$1</strong>'],
    [/\{\\(?:itshape|slshape|emph|em|it|sl)(?![a-zA-Z])\s*([^{}]*)\}/g, '<em>$1</em>'],
    [/\{\\(?:ttfamily|tt)(?![a-zA-Z])\s*([^{}]*)\}/g, '<code>$1</code>'],
    [/\{\\(?:normalfont|rmfamily|sffamily|scshape|rm|sf|sc)(?![a-zA-Z])\s*([^{}]*)\}/g, '$1'],
    [/\\(?:texttt|verb|lstinline)\{([^{}]*)\}/g, '<code>$1</code>'],
    [/\\href\{([^{}]*)\}\{([^{}]*)\}/g,
      (_m: string, href: string, label: string) => `<a class="tex-link" href="${attrValue(href)}" target="_blank" rel="noopener">${label}</a>`],
    [/\\url\{([^{}]*)\}/g,
      (_m: string, href: string) => `<a class="tex-link tex-url" href="${attrValue(href)}" target="_blank" rel="noopener">${href.replace(/-/g, '&#45;')}</a>`],
    [/\\texorpdfstring\{([^{}]*)\}\{[^{}]*\}/g, '$1'],
    // cleveref's \cref/\Cref/\crefrange and plain \ref all render as "<name> <num>";
    // \eqref is the one that shows the bare number, in parentheses
    [/\\[cC]ref(?:range)?\{([^{}]*)\}(?:\{([^{}]*)\})?/g,
      (_m: string, a: string, b?: string) => xref(b ? `${a},${b}` : a, refs)],
    [/\\eqref\{([^{}]*)\}/g, (_m: string, a: string) => xref(a, refs, true)],
    [/\\ref\{([^{}]*)\}/g, (_m: string, a: string) => xref(a, refs)],
    // cross-project cite. Two-arg form first so the bare-handle rule below only
    // ever sees `\citeext{Handle}` with no label brace.
    [/\\citeext\{([^{}]*)\}\{([^{}]*)\}/g, (_m: string, h: string, l: string) => extref(h.trim(), l.trim())],
    [/\\citeext\{([^{}]*)\}/g, (_m: string, h: string) => extref(h.trim(), null)],
    [
      /\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])?\{([^{}]*)\}/g,
      (_m: string, a: string) =>
        a
          .split(',')
          .map((k) => {
            k = k.trim();
            // number it as LaTeX would; an unresolved key shows itself, which
            // is the useful thing to see when a \cite has no .bib entry
            const n = cites[k];
            return `<a class="cite" data-cite="${esc(k)}">[${n ?? esc(k)}]</a>`;
          })
          .join(', '),
    ],
  ];
}

function inlineMacros(s: string, refs: Record<string, RefEntry>, cites: CiteNums): string {
  let prev: string;
  let i = 0;
  const rules = imRules(refs, cites);
  do {
    prev = s;
    for (const [re, rep] of rules) s = s.replace(re, rep as never);
  } while (s !== prev && ++i < 10);
  return s;
}

const ACCENTS: Record<string, string> = {
  "'": '́', '`': '̀', '^': '̂', '"': '̈', '~': '̃',
  '=': '̄', '.': '̇', v: '̌', u: '̆', c: '̧', H: '̋', r: '̊',
};

/** Apply TeX's prose ligatures to visible text without rewriting attributes
 * inside the HTML emitted by `inlineMacros` (notably `--` inside a URL). */
function texTypography(s: string): string {
  return s
    .split(/(<(?:[^>"']|"[^"]*"|'[^']*')*>)/g)
    .map((part) =>
      part.startsWith('<')
        ? part
        : part.replace(/``/g, '“').replace(/''/g, '”').replace(/---/g, '—').replace(/--/g, '–'),
    )
    .join('');
}

/** The source has already gone through `esc`, so only quote characters need
 * escaping here. Keeping this separate avoids double-encoding URL ampersands. */
function attrValue(s: string): string {
  return s.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function detexRest(s: string): string {
  s = s.replace(
    /\\(['`^"~=.]|[vucHr](?![A-Za-z]))(?:\s*\{([A-Za-z])\}|([A-Za-z]))/g,
    (_m, a, br, ba) => ((br || ba || '') + ACCENTS[a]).normalize('NFC'),
  );
  s = texTypography(s);
  s = s.replace(
    /\\(?:noindent|indent|par|smallskip|medskip|bigskip|vfill|hfill|newpage|clearpage|pagebreak|nopagebreak|linebreak|centering|raggedright|raggedleft|samepage|sloppy|protect|leavevmode|frenchspacing|allowbreak|maketitle|bfseries|itshape|normalfont|scshape|ttfamily|footnotesize|small|large|Large|normalsize)\b\s*/g,
    '',
  );
  s = s.replace(/\\item\s*\[([^\]]*)\]\s*/g, '</li><li class="li-lbl"><span class="li-mark">$1</span> ');
  s = s
    .replace(/\\begin\{itemize\}/g, '<ul>')
    .replace(/\\end\{itemize\}/g, '</ul>')
    .replace(/\\begin\{enumerate\}/g, '<ol>')
    .replace(/\\end\{enumerate\}/g, '</ol>')
    .replace(/\\begin\{description\}/g, '<ul>')
    .replace(/\\end\{description\}/g, '</ul>')
    .replace(/\\item\s*/g, '</li><li>');
  s = s.replace(/<(ul|ol)><\/li>/g, '<$1>');
  s = s.replace(/\\(?:label|hspace\*?|vspace\*?|phantom|hphantom|vphantom|vskip|hskip|setlength|index|footnotemark)\{[^{}]*\}/g, '');
  s = s
    .replace(/\\(?:dcref|group|level|lean|uses|proves|label|source)\{[^{}]*\}/g, '')
    .replace(/\\(?:leanok|notready|mathlibok|sketch)\b/g, '');
  s = s.replace(/\\footnote\{([^{}]*)\}/g, ' ($1)');
  s = s.replace(/\\begin\{quote\}/g, '<blockquote>').replace(/\\end\{quote\}/g, '</blockquote>');
  const envLbl = (_m: string, e: string) => `<em class="env-lbl">${e.charAt(0).toUpperCase() + e.slice(1)}.</em> `;
  s = s
    .replace(/\\begin\{(proof|claim|lemma|theorem|proposition|corollary|definition|remark|example|conjecture|sublemma|scholium|note)\}\s*/g, envLbl as never)
    .replace(/\\end\{(?:proof|claim|lemma|theorem|proposition|corollary|definition|remark|example|conjecture|sublemma|scholium|note)\}\s*/g, ' ');
  s = s.replace(/\\(?:begin|end)\{[a-zA-Z*]+\}\s*/g, '');
  s = s.replace(
    /\\(?:it|rm|bf|sl|sc|tt|sf|em|quad|qquad|nobreak|goodbreak|hfil|hfill|vfil|vfill|thinspace|enspace|display|textstyle|scriptstyle|displaystyle)\b\s*/g,
    '',
  );
  s = s
    .replace(/\{\\v ([A-Za-z])\}/g, '$1̌')
    .replace(/\\%/g, '%')
    .replace(/\\&/g, '&amp;')
    .replace(/\\#/g, '#')
    .replace(/\\_/g, '_')
    .replace(/\\ /g, ' ')
    .replace(/\\,|\\;|\\!|\\:/g, ' ');
  s = s.replace(/\\\{/g, '&#123;').replace(/\\\}/g, '&#125;');
  s = s.replace(/\\\\\s*/g, '<br>').replace(/(?<!\\)~/g, ' ');
  s = s.replace(/\{\\(?:[a-zA-Z]+)\b\s*|[{}]/g, '');
  s = s.replace(/[ \t]*\n[ \t]*\n[ \t]*/g, '</p><p>');
  s = s.replace(/[ \t]{2,}/g, ' ');
  return s;
}

/** Wrap standalone display-math environments so KaTeX renders them. */
function mathEnvs(s: string): string {
  const strip = (b: string) =>
    b.replace(/\\label\{[^{}]*\}/g, '').replace(/\\(?:notag|nonumber)\b/g, '').replace(/(\\begin\{array\})\s*\[[a-zA-Z]\]/g, '$1');
  // Each numbered equation carries its number as a `\tag{…}` the backend wrote
  // in (see dashboard._number_equations) — KaTeX draws it where LaTeX would.
  // Mirror every tag as an empty anchor just before the display so `\cref{eq:…}`
  // has somewhere to scroll to; the sentinel survives esc() and becomes HTML at
  // the end of detex().
  const anchors = (b: string) =>
    (b.match(/\\tag\*?\{([\w.]+)\}/g) || [])
      .map((t) => `@@EQ${t.replace(/^\\tag\*?\{|\}$/g, '')}QE@@`)
      .join('');
  const M: string[] = [];
  const prot = (x: string) =>
    x.replace(/(\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$|\$[^$]*?\$)/g, (m) => {
      M.push(m);
      return '@@KE' + (M.length - 1) + 'EK@@';
    });
  s = prot(s);
  s = s.replace(/\\begin\{equation\*?\}([\s\S]*?)\\end\{equation\*?\}/g, (_m, b) => `${anchors(b)}\\[${strip(b)}\\]`);
  s = s.replace(
    /\\begin\{(eqnarray\*?|align\*?|alignat\*?|flalign\*?|gather\*?|multline\*?)\}([\s\S]*?)\\end\{\1\}/g,
    (_m, env, b) => {
      const inner = /^gather/.test(env) ? 'gathered' : 'aligned';
      const a = anchors(b);
      if (/^eqnarray/.test(env)) b = b.replace(/&\s*([^&\n]*?)\s*&/g, '&$1');
      else if (/^alignat/.test(env)) b = b.replace(/^\s*\{?\d+\}?/, '');
      return `${a}\\[\\begin{${inner}}${strip(b)}\\end{${inner}}\\]`;
    },
  );
  s = prot(s);
  s = s.replace(
    /(\\begin\{(aligned|alignedat|gathered|split|array|cases|dcases|smallmatrix|matrix|bmatrix|Bmatrix|pmatrix|vmatrix|Vmatrix)\}[\s\S]*?\\end\{\2\})/g,
    (m) => `\\[${strip(m)}\\]`,
  );
  return s.replace(/@@KE(\d+)EK@@/g, (_m, i) => M[+i]);
}

/** Text-mode LaTeX -> HTML; math is pulled to sentinels first so text macros
 * resolve even across math, then restored verbatim for KaTeX. */
export function detex(
  s: string | null | undefined,
  refs: Record<string, RefEntry> = {},
  cites: CiteNums = {},
): string {
  // `\$` is a literal dollar, not a math delimiter — pull it out before the
  // math-protection regexes below (and mathEnvs') can mistake it for one,
  // and restore it as an entity so KaTeX's auto-render won't re-read it
  s = String(s || '').replace(/\\\$/g, '@@KDOLLARK@@');
  s = esc(mathEnvs(s));
  const math: string[] = [];
  s = s.replace(/(\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$|\$[^$]*?\$)/g, (m) => {
    math.push(m);
    return '@@KX' + (math.length - 1) + 'XK@@';
  });
  s = detexRest(inlineMacros(s, refs, cites));
  return s
    .replace(/@@KX(\d+)XK@@/g, (_m, i) => math[+i])
    .replace(/@@KDOLLARK@@/g, '&#36;')
    .replace(/@@EQ(.*?)QE@@/g, (_m, n) => `<span class="eqa" id="eq-${n}"></span>`);
}

export function proseHtml(
  s: string | null | undefined,
  refs: Record<string, RefEntry> = {},
  cites: CiteNums = {},
): string {
  const h = '<p>' + detex(s, refs, cites) + '</p>';
  return h.replace(/<p>\s*<\/p>/g, '');
}

/** Strip all TeX markup down to plain text (titles used outside prose flow, e.g. tooltips). */
export function plainTex(s?: string | null): string {
  return String(s || '')
    .replace(/\\[a-zA-Z]+\s?/g, ' ')
    .replace(/[{}$\\]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/** Minimal Lean syntax highlighting: keywords + comments. */
export function leanHi(code: string): string {
  let s = esc(code);
  const cm: string[] = [];
  s = s.replace(/(\/-[\s\S]*?-\/|--[^\n]*)/g, (m) => {
    cm.push(m);
    return '@@CM' + (cm.length - 1) + '@@';
  });
  s = s.replace(
    /\b(theorem|lemma|def|abbrev|instance|structure|class|inductive|where|by|fun|let|in|match|with|do|if|then|else|from|have|show|calc|open|namespace|end|variable|universe|section|example|noncomputable|private|protected|import)\b/g,
    '<span class="c-kw">$1</span>',
  );
  s = s.replace(/@@CM(\d+)@@/g, (_m, i) => `<span class="c-cm">${cm[+i]}</span>`);
  return s;
}
