import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const webui = fileURLToPath(new URL('../../hgraph/webui/', import.meta.url));
const entries = ['lean_ok', 'empty'].map((lean_status, i) => ({
  id: `node-${i}`, label: `thm:${i}`, title: `Statement ${i}`, chapter: 'Chapter',
  kind: 'theorem', body: 'A statement.', lean_status, lean: [], deps: [],
  reviews: [], comments: [], reviewed: false, sketch: false,
}));
const chapter = { title: 'Chapter', num: '1', blocks: entries.map(e => ({
  t: 'stmt', ...e, content_type: 'theorem', num: `1.${e.id.slice(-1)}`, abbr: 'Thm',
  labels: [e.label], lean: [], uses: [], leanok: false, mathlibok: false, enrich: e,
})) };
const project = progress => ({ title: 'Fixture', mode: 'doc', progress, entries,
  chapters: [chapter], refs: {}, bib: [], macros: {}, repo: null });
const card = (root, progress) => ({ name: root, root, category: null, progress,
  stats: { statements: 2, done: 1, partial: 0, todo: 1, pct: progress === false ? null : 50 } });
let cards = [card('exposition', false), card('legacy', undefined)];
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (/\/(exposition|legacy)\/(project|data)\.json$/.test(url.pathname)) {
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify(project(url.pathname.includes('exposition') ? false : undefined)));
    return;
  }
  const file = path.join(webui, url.pathname === '/' ? 'index.html' : url.pathname);
  if (!file.startsWith(webui) || !fs.existsSync(file)) { res.writeHead(404).end(); return; }
  res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
  if (url.pathname === '/') {
    const data = { title: 'Fixture', sections: [{ category: null, projects: cards }] };
    res.end(fs.readFileSync(file, 'utf8').replace('</head>', `<script>window.__HGRAPH_DATA__=${JSON.stringify(data)}</script></head>`));
  } else res.end(fs.readFileSync(file));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch();
try {
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 1000 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    cards = [card('exposition', false), card('legacy', undefined)];
    await page.goto(origin);
    await page.locator('.card').first().waitFor();
    assert.equal(await page.locator('.site-header .pbar').count(), 0);
    assert.equal(await page.locator('.card[href="#/exposition"] .card-pct').count(), 0);
    assert.equal(await page.locator('.card[href="#/legacy"] .card-pct').innerText(), '50%');
    for (const [root, progress] of [['exposition', false], ['legacy', true]]) {
      await page.goto(`${origin}/#/${root}#ch-1`);
      await page.locator('.choverview').waitFor();
      assert.equal((await page.locator('.choverview').innerText()).includes('50%'), progress);
      assert.equal(await page.locator('.project-header .pbar').count(), progress ? 1 : 0);
      const summaryLink = page.locator('.navlink').filter({ hasText: progress ? 'Blueprint summary' : 'Source links' });
      if (width <= 900) await page.getByLabel('Blueprint view', { exact: true }).selectOption('summary');
      else await summaryLink.click();
      await page.locator('h2.ch').waitFor();
      if (!progress) {
        assert.match(await page.locator('main').innerText(), /1 of 2 statements have resolved source annotations/);
        assert.doesNotMatch(await page.locator('main').innerText(), /%|Ready next|Current blockers|Fully closed/);
      }
    }
    cards = [card('legacy', undefined)];
    await page.goto(origin);
    await page.locator('.site-header .pbar').waitFor();
    assert.match(await page.locator('.site-header').innerText(), /50%/);
    assert.deepEqual(errors, []);
    await page.close();
  }
  console.log('Progress display: desktop/mobile, default/opt-out, mixed workspace passed');
} finally {
  await browser.close();
  server.close();
}
