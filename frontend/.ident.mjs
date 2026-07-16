import { chromium } from 'playwright';
const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1500, height: 1000 } });
await page.goto(process.argv[2] + '/#/examples/gauss', { waitUntil: 'networkidle' });
await page.locator('.navlink', { hasText: 'Dependency graph' }).click();
await page.waitForSelector('.graph-modal svg');
await page.locator('.graph-modal g.node').first().click();
await page.waitForSelector('.graph-modal g.cluster');
await page.evaluate(() => {
  document.querySelector('.gv-canvas').__mine = 'canvas';
  document.querySelector('.gv-inner').__mine = 'inner';
  document.querySelector('.gv-inner svg').__mine = 'svg';
});
const t0 = await page.locator('.gv-inner').evaluate((el) => el.style.transform);
await page.locator('.graph-modal g.node[data-nid]:not([data-nid^="ch"])').first().click();
await page.waitForTimeout(400);
const r = await page.evaluate(() => ({
  canvasSame: document.querySelector('.gv-canvas').__mine === 'canvas',
  innerSame: document.querySelector('.gv-inner').__mine === 'inner',
  svgSame: document.querySelector('.gv-inner svg')?.__mine === 'svg',
  transform: document.querySelector('.gv-inner').style.transform,
}));
console.log('before stmt click transform:', t0);
console.log(JSON.stringify(r, null, 1));
await b.close();
