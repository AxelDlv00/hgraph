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
  id: string | null;
  abbr: string;
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

/** `\ref{a,b}` / `\cref{a,b}` -> numbered links (or a plain xref span if unresolved). */
export function xref(labels: string, refs: Record<string, RefEntry>): string {
  return labels
    .split(',')
    .map((l) => {
      l = l.trim();
      const r = refs[l];
      if (r && r.id) return `<a class="ref" data-id="${r.id}">${r.abbr}&nbsp;${r.num}</a>`;
      if (r) return `<span class="ref" style="color:var(--muted);cursor:default">${r.abbr}&nbsp;${r.num}</span>`;
      return `<span class="xref">${esc(l.replace(/^[a-z]+:/, ''))}</span>`;
    })
    .join(', ');
}

// Resolve text-formatting macros innermost-first so nested braces render, e.g.
// \textit{Source: \texttt{Foo.Bar} in \texttt{A/B.lean}, L44--L440} -> all levels.
function imRules(refs: Record<string, RefEntry>, cites: CiteNums): [RegExp, string | ((...a: string[]) => string)][] {
  return [
    [/\\paragraph\{([^{}]*)\}/g, '<b>$1.</b> '],
    [/\\(?:sub)*section\*?\{([^{}]*)\}/g, '<strong>$1</strong> '],
    [/\\(?:emph|textit|textsl|textsc)\{([^{}]*)\}/g, '<em>$1</em>'],
    [/\\textbf\{([^{}]*)\}/g, '<strong>$1</strong>'],
    [/\{\\(?:bfseries|bf)(?![a-zA-Z])\s*([^{}]*)\}/g, '<strong>$1</strong>'],
    [/\{\\(?:itshape|slshape|emph|em|it|sl)(?![a-zA-Z])\s*([^{}]*)\}/g, '<em>$1</em>'],
    [/\{\\(?:ttfamily|tt)(?![a-zA-Z])\s*([^{}]*)\}/g, '<code>$1</code>'],
    [/\{\\(?:normalfont|rmfamily|sffamily|scshape|rm|sf|sc)(?![a-zA-Z])\s*([^{}]*)\}/g, '$1'],
    [/\\(?:texttt|verb|lstinline)\{([^{}]*)\}/g, '<code>$1</code>'],
    [/\\href\{([^{}]*)\}\{([^{}]*)\}/g, '<a href="$1" target="_blank" rel="noopener">$2</a>'],
    [/\\url\{([^{}]*)\}/g, '<a href="$1" target="_blank" rel="noopener">$1</a>'],
    [/\\texorpdfstring\{([^{}]*)\}\{[^{}]*\}/g, '$1'],
    [/\\[cC]ref\{([^{}]*)\}/g, (_m: string, a: string) => xref(a, refs)],
    [/\\(?:eq)?ref\{([^{}]*)\}/g, (_m: string, a: string) => xref(a, refs)],
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

function detexRest(s: string): string {
  s = s.replace(
    /\\(['`^"~=.]|[vucHr](?![A-Za-z]))(?:\s*\{([A-Za-z])\}|([A-Za-z]))/g,
    (_m, a, br, ba) => ((br || ba || '') + ACCENTS[a]).normalize('NFC'),
  );
  s = s.replace(/``/g, '“').replace(/''/g, '”').replace(/---/g, '—').replace(/ -- /g, ' – ');
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
    .replace(/\\(?:leanok|notready|mathlibok)\b/g, '');
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
  const M: string[] = [];
  const prot = (x: string) =>
    x.replace(/(\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$|\$[^$]*?\$)/g, (m) => {
      M.push(m);
      return '@@KE' + (M.length - 1) + 'EK@@';
    });
  s = prot(s);
  s = s.replace(/\\begin\{equation\*?\}([\s\S]*?)\\end\{equation\*?\}/g, (_m, b) => `\\[${strip(b)}\\]`);
  s = s.replace(
    /\\begin\{(eqnarray\*?|align\*?|alignat\*?|flalign\*?|gather\*?|multline\*?)\}([\s\S]*?)\\end\{\1\}/g,
    (_m, env, b) => {
      const inner = /^gather/.test(env) ? 'gathered' : 'aligned';
      if (/^eqnarray/.test(env)) b = b.replace(/&\s*([^&\n]*?)\s*&/g, '&$1');
      else if (/^alignat/.test(env)) b = b.replace(/^\s*\{?\d+\}?/, '');
      return `\\[\\begin{${inner}}${strip(b)}\\end{${inner}}\\]`;
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
  return s.replace(/@@KX(\d+)XK@@/g, (_m, i) => math[+i]).replace(/@@KDOLLARK@@/g, '&#36;');
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
