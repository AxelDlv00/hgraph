import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { chromium } from 'playwright';

const server = await createServer({ server: { host: '127.0.0.1', port: 0 }, plugins: [{
  name: 'rendering-fixture',
  configureServer(server) {
    server.middlewares.use('/rendering-fixture', async (_req, res) => {
      res.setHeader('Content-Type', 'text/html');
      res.end(await server.transformIndexHtml('/rendering-fixture', '<!doctype html><html><head></head><body><div id="root"></div><script type="module" src="/tests/rendering-fixture.tsx"></script></body></html>'));
    });
  },
}] });
await server.listen();
const browser = await chromium.launch();
try {
  const { leanSourceUrl } = await server.ssrLoadModule('/src/sourceUrl.ts');
  assert.equal(leanSourceUrl('../shared/A B.lean', 'owner/repo', 'Project'), 'https://github.com/owner/repo/blob/main/shared/A%20B.lean');
  assert.equal(leanSourceUrl('/private/file.lean', 'owner/repo', 'Project'), null);
  assert.equal(leanSourceUrl('../../file.lean', 'owner/repo', 'Project'), null);
  assert.equal(leanSourceUrl('file.lean', null, 'Project'), null);
  const { detex } = await server.ssrLoadModule('/src/latex.ts');
  assert.equal(detex(String.raw`\chaptermark{Title}\bibliographyrefs{refs}Text`), 'Text');
  const { sourceLinkLabel } = await server.ssrLoadModule('/src/progress.ts');
  assert.equal(sourceLinkLabel('lean_ok'), 'lean ok');
  assert.equal(sourceLinkLabel('mathlib_ok'), 'mathlib ok');
  assert.equal(sourceLinkLabel('empty'), 'not formalized');
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`${server.resolvedUrls.local[0]}rendering-fixture`);
    await page.waitForFunction(() => document.querySelectorAll('#math .katex').length === 3);
    assert.equal(await page.locator('.katex-error').count(), 0);
    await page.evaluate(() => {
      window.typesetNode = document.querySelector('#math .katex');
      window.mathMutations = 0;
      new MutationObserver(records => { window.mathMutations += records.length; })
        .observe(document.getElementById('math'), { childList: true, subtree: true });
    });
    for (let i = 0; i < 5; i++) await page.getByRole('button').click();
    assert.equal(await page.evaluate(() => document.querySelector('#math .katex') === window.typesetNode), true);
    assert.equal(await page.evaluate(() => window.mathMutations), 0);
    assert.equal(await page.getByRole('link').getAttribute('href'), 'https://github.com/frenzymath/Poincare-Conjecture/blob/main/PoincareConjecture/PoincareLib/Geometry.lean');
    assert.deepEqual(errors, []);
    await page.close();
  }
  console.log('Rendering: display environments, stable KaTeX DOM, source URLs, status labels passed');
} finally {
  await browser.close();
  await server.close();
}
