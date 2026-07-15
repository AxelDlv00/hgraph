// Validates every math span in the blueprint against real KaTeX, so broken math is
// caught as a warning before serving/exporting rather than discovered as a blank
// render in the browser. Mirrors the client's mathEnvs() wrapping (dashboard.py's JS)
// so it tests exactly what KaTeX is actually asked to render.
//
// stdin:  {"items": [{"ref": "...", "text": "..."}], "macros": {"\\foo": "..."}}
// stdout: {"totalSpans": N, "errors": [{"ref", "display", "content", "message"}]}
"use strict";
const katex = require("katex");

function stripEnvNoise(b) {
  return b.replace(/\\label\{[^{}]*\}/g, "")
          .replace(/\\(?:notag|nonumber)\b/g, "")
          .replace(/(\\begin\{array\})\s*\[[a-zA-Z]\]/g, "$1");
}

function mathEnvs(s) {
  const M = [];
  const prot = x => x.replace(/(\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$|\$[^$]*?\$)/g,
    m => { M.push(m); return "@@KE" + (M.length - 1) + "EK@@"; });
  s = prot(s);
  s = s.replace(/\\begin\{equation\*?\}([\s\S]*?)\\end\{equation\*?\}/g,
    (m, b) => `\\[${stripEnvNoise(b)}\\]`);
  s = s.replace(/\\begin\{(eqnarray\*?|align\*?|alignat\*?|flalign\*?|gather\*?|multline\*?)\}([\s\S]*?)\\end\{\1\}/g,
    (m, env, b) => {
      const inner = /^gather/.test(env) ? "gathered" : "aligned";
      if (/^eqnarray/.test(env)) b = b.replace(/&\s*([^&\n]*?)\s*&/g, "&$1");
      else if (/^alignat/.test(env)) b = b.replace(/^\s*\{?\d+\}?/, "");
      return `\\[\\begin{${inner}}${stripEnvNoise(b)}\\end{${inner}}\\]`;
    });
  s = prot(s);
  s = s.replace(/(\\begin\{(aligned|alignedat|gathered|split|array|cases|dcases|smallmatrix|matrix|bmatrix|Bmatrix|pmatrix|vmatrix|Vmatrix)\}[\s\S]*?\\end\{\2\})/g,
    m => `\\[${stripEnvNoise(m)}\\]`);
  return s.replace(/@@KE(\d+)EK@@/g, (_, i) => M[+i]);
}

function extractMathSpans(s) {
  const spans = [];
  const re = /(\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$|\$[^$]*?\$)/g;
  let m;
  while ((m = re.exec(s))) {
    const raw = m[0];
    let display, content;
    if (raw.startsWith("\\[")) { display = true; content = raw.slice(2, -2); }
    else if (raw.startsWith("\\(")) { display = false; content = raw.slice(2, -2); }
    else if (raw.startsWith("$$")) { display = true; content = raw.slice(2, -2); }
    else { display = false; content = raw.slice(1, -1); }
    spans.push({ display, content });
  }
  return spans;
}

let input = "";
process.stdin.on("data", d => (input += d));
process.stdin.on("end", () => {
  const { items, macros: macrosRaw } = JSON.parse(input);
  const macros = Object.assign({ "\\mbox": "\\text", "\\hbox": "\\text" }, macrosRaw || {});
  const errors = [];
  let totalSpans = 0;
  for (const { ref, text } of items) {
    const wrapped = mathEnvs(text || "");
    for (const { display, content } of extractMathSpans(wrapped)) {
      totalSpans++;
      try {
        katex.renderToString(content, {
          macros: Object.assign({}, macros), displayMode: display,
          throwOnError: true, trust: true, strict: "ignore",
        });
      } catch (e) {
        errors.push({ ref, display, content: content.slice(0, 160), message: e.message.split("\n")[0] });
      }
    }
  }
  process.stdout.write(JSON.stringify({ totalSpans, errors }));
});
