import { chromium } from 'playwright';

const base = process.argv[2];
const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1500, height: 1000 } });
const errs = [];
const clog = [];
page.on('pageerror', (e) => errs.push('pageerror: ' + e.message));
page.on('console', (m) => m.type() === 'error' && errs.push('console: ' + m.text()));

// --- project view: overview -> chapter, math typesets, hydration completes --
await page.goto(base + '/#/examples/gauss', { waitUntil: 'networkidle' });
await page.waitForTimeout(400);
console.log('project title:', await page.locator('.project-htop h1').innerText());

// go to chapter 1 via the overview drill-down / TOC
await page.locator('.tch', { hasText: '1' }).first().click();
await page.waitForTimeout(900); // idle hydration + lazy KaTeX
const pending = await page.locator('.blk-pending').count();
const katex = await page.locator('.doc .katex').count();
const stmts = await page.locator('.doc .stmt').count();
console.log(`chapter view: stmts=${stmts} katex=${katex} pending-placeholders=${pending}`);

// --- deep link straight into a statement (anchor force-mount path) ----------
await page.goto(base + '/#/examples/gauss#thm:gauss', { waitUntil: 'networkidle' }).catch(() => {});
await page.waitForTimeout(300);

// --- graph modal -------------------------------------------------------------
await page.locator('.navlink', { hasText: 'Dependency graph' }).click();
await page.waitForSelector('.graph-modal svg', { timeout: 8000 });
const boxes = await page.locator('.graph-modal g.node').count();
console.log('graph modal open, collapsed chapter boxes:', boxes);

const t0 = await page.locator('.gv-inner').evaluate((el) => el.style.transform);

// wheel WITHOUT ctrl -> should PAN (translate changes, scale unchanged)
await page.locator('.gv-canvas').hover();
await page.mouse.wheel(0, 120);
await page.waitForTimeout(120);
const t1 = await page.locator('.gv-inner').evaluate((el) => el.style.transform);

// wheel WITH ctrl -> should ZOOM (scale changes)
await page.keyboard.down('Control');
await page.mouse.wheel(0, -240);
await page.keyboard.up('Control');
await page.waitForTimeout(120);
const t2 = await page.locator('.gv-inner').evaluate((el) => el.style.transform);
console.log('transform initial:', t0);
console.log('after plain wheel:', t1);
console.log('after ctrl+wheel :', t2);

// drag -> pan
const canvas = await page.locator('.gv-canvas').boundingBox();
await page.mouse.move(canvas.x + 400, canvas.y + 300);
await page.mouse.down();
await page.mouse.move(canvas.x + 480, canvas.y + 360, { steps: 8 });
await page.mouse.up();
const t3 = await page.locator('.gv-inner').evaluate((el) => el.style.transform);
console.log('after drag       :', t3);

// click a collapsed chapter box -> expands into a cluster (worker layout)
await page.locator('.graph-modal g.node').first().click();
await page.waitForSelector('.graph-modal g.cluster', { timeout: 15000 });
const clusters = await page.locator('.graph-modal g.cluster').count();
const nodesNow = await page.locator('.graph-modal g.node').count();
console.log(`expanded: clusters=${clusters} nodes=${nodesNow}`);

// click a statement node -> side panel shows the statement card
const stmtNode = page.locator('.graph-modal g.node[data-nid]:not([data-nid^="ch"])').first();
await stmtNode.click();
await page.waitForTimeout(400);
const side = await page.locator('#gm-side').innerText().catch(() => '(none)');
console.log('side panel:', side.slice(0, 60).replace(/\n/g, ' '));

// cluster background click -> collapses back
await page.locator('.gm-btn', { hasText: 'Fit' }).click();
await page.waitForTimeout(150);
// find a screen point that hit-tests to the cluster background (not a node)
const pt = await page.evaluate(() => {
  const path = document.querySelector('.graph-modal g.cluster > path, .graph-modal g.cluster > polygon');
  const r = path.getBoundingClientRect();
  for (let dx = 4; dx < r.width / 2; dx += 3)
    for (const fy of [0.5, 0.35, 0.65]) {
      const x = r.left + dx, y = r.top + r.height * fy;
      const el = document.elementFromPoint(x, y);
      if (el && el.closest('g.cluster') && !el.closest('g.node')) return { x, y };
    }
  return null;
});
console.log('collapse click point:', JSON.stringify(pt));
await page.evaluate(() => {
  document.querySelector('.gv-canvas').addEventListener('click', (e) => {
    console.log('CANVAS CLICK target=' + e.target.tagName + ' node=' + !!e.target.closest('g.node') + ' cluster=' + !!e.target.closest('g.cluster'));
  }, true);
});
await page.mouse.move(pt.x, pt.y);
await page.waitForTimeout(300);
const probe = await page.evaluate(({ x, y }) => {
  const el = document.elementFromPoint(x, y);
  let chain = [];
  for (let e = el; e && chain.length < 6; e = e.parentElement) chain.push(e.tagName + (e.className.baseVal !== undefined ? '.' + e.className.baseVal : '.' + (e.className || '')).slice(0, 30));
  document.addEventListener('pointerdown', (e) => console.log('CANVASDOC pointerdown on ' + e.target.tagName), { capture: true, once: true });
  document.addEventListener('click', (e) => console.log('CANVASDOC click on ' + e.target.tagName + ' defaultPrevented=' + e.defaultPrevented), { capture: true, once: true });
  return chain.join(' > ');
}, pt);
console.log('under cursor before click:', probe);
await page.evaluate(() => {
  window.__evlog = [];
  for (const ty of ['pointerdown', 'pointerup', 'mousedown', 'click'])
    document.addEventListener(ty, (e) => window.__evlog.push(ty + ':' + e.target.tagName), true);
});
console.log('pre-click state:', await page.evaluate(() => JSON.stringify({
  canvases: document.querySelectorAll('.gv-canvas').length,
  modals: document.querySelectorAll('.graph-modal').length,
  clusterDataCh: document.querySelector('.graph-modal g.cluster')?.dataset.ch,
  svgs: document.querySelectorAll('.gv-inner svg').length,
})));
await page.mouse.click(pt.x, pt.y);
console.log('event log:', await page.evaluate(() => window.__evlog.join(' ')));
await page.waitForTimeout(600);
console.log('after cluster-bg click, clusters:', await page.locator('.graph-modal g.cluster').count());

console.log('page log:', clog.filter((l) => l.startsWith('CANVAS')).join(' | ') || '(no canvas click seen)');
console.log('errors:', errs.length ? errs.slice(0, 4) : 'none');
await b.close();
