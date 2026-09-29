import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
after(() => server.close());
const { Docstring } = await server.ssrLoadModule('/src/components/Docstring.tsx');
const render = text => renderToStaticMarkup(createElement(Docstring, { text }));

test('renders Lean documentation prose, emphasis and inline identifiers', () => {
  const html = render('**Math.** The *Morgan-Tian* convention uses `R(X,Y)Z`.\n\nBlueprint: `def:curvature`.');
  assert.match(html, /<strong>Math\.<\/strong>/);
  assert.match(html, /<em>Morgan-Tian<\/em>/);
  assert.match(html, /<code>R\(X,Y\)Z<\/code>/);
  assert.match(html, /<code>def:curvature<\/code>/);
  assert.doesNotMatch(html, /\*\*Math/);
});

test('uses an initially expanded, native disclosure', () => {
  const html = render('Documentation');
  assert.match(html, /<details class="lean-docstring" open="">/);
  assert.match(html, /<summary>Documentation<\/summary>/);
});

test('supports links, lists, tables and fenced Lean blocks', () => {
  const html = render('- [Reference](https://example.org)\n\n| A | B |\n|---|---|\n| x | y |\n\n```lean\ntheorem t : True := by trivial\n```');
  assert.match(html, /<ul>/);
  assert.match(html, /href="https:\/\/example.org"/);
  assert.match(html, /<table>/);
  assert.match(html, /<pre><code class="language-lean">/);
});

test('does not execute raw HTML or allow script links', () => {
  const html = render('<img src=x onerror=alert(1)>\n\n[bad](javascript:alert%281%29)');
  assert.doesNotMatch(html, /<img|onerror|javascript:/);
});
