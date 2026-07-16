import { chromium } from 'playwright';
const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1500, height: 1000 } });
const probe = () =>
  page.evaluate(() => ({
    tagged: document.querySelectorAll('.graph-modal g.node[data-nid]').length,
    nodes: document.querySelectorAll('.graph-modal g.node').length,
    ch: document.querySelector('.graph-modal g.cluster')?.dataset.ch ?? 'NONE',
    titles: document.querySelectorAll('.graph-modal svg title').length,
  }));
await page.goto(process.argv[2] + '/#/examples/gauss', { waitUntil: 'networkidle' });
await page.locator('.navlink', { hasText: 'Dependency graph' }).click();
await page.waitForSelector('.graph-modal svg');
console.log('after open      :', JSON.stringify(await probe()));
await page.locator('.graph-modal g.node').first().click();
await page.waitForSelector('.graph-modal g.cluster');
console.log('after expand    :', JSON.stringify(await probe()));
await page.waitForTimeout(1500); // let prefetch finish
console.log('after idle 1.5s :', JSON.stringify(await probe()));
const stmtNode = page.locator('.graph-modal g.node[data-nid]:not([data-nid^="ch"])').first();
await stmtNode.click();
await page.waitForTimeout(400);
console.log('after stmt click:', JSON.stringify(await probe()));
await page.locator('.gm-btn', { hasText: 'Fit' }).click();
await page.waitForTimeout(200);
console.log('after Fit       :', JSON.stringify(await probe()));
await b.close();
