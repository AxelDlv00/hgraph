import { chromium } from 'playwright';
const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1500, height: 1000 } });
page.on('console', (m) => console.log('|', m.text().slice(0, 160)));
await page.goto(process.argv[2] + '/#/examples/gauss', { waitUntil: 'networkidle' });
await page.locator('.navlink', { hasText: 'Dependency graph' }).click();
await page.waitForSelector('.graph-modal svg');
await page.locator('.graph-modal g.node').first().click();
await page.waitForSelector('.graph-modal g.cluster');
const info = await page.evaluate(() => {
  const c = document.querySelector('.graph-modal g.cluster');
  const kids = [...c.children].map((k) => k.tagName).join(',');
  document.querySelector('.gv-canvas').addEventListener('click', (e) => {
    const t = e.target;
    console.log('click target:', t.tagName, '| closest node:', !!t.closest('g.node'), '| closest cluster:', !!t.closest('g.cluster'));
  }, true);
  return { dataCh: c.dataset.ch, id: c.id, kids };
});
console.log('cluster:', JSON.stringify(info));
const cbb = await page.locator('.graph-modal g.cluster path, .graph-modal g.cluster polygon').first().boundingBox();
console.log('path bbox:', JSON.stringify(cbb));
await page.mouse.click(cbb.x + 8, cbb.y + cbb.height / 2);
await page.waitForTimeout(800);
console.log('clusters now:', await page.locator('.graph-modal g.cluster').count());
await b.close();
