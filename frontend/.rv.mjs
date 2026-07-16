import { chromium } from 'playwright';
const OUT='/tmp/claude-1001/-home-axel-HyperGraph/cdc3fa11-48ef-4738-a2fb-df3952785bde/scratchpad/shots';
const [base, root, expectStatic, expectRepo, shot] = process.argv.slice(2);
const wantStatic = expectStatic==='1', wantRepo = expectRepo==='1';
const b=await chromium.launch();
const page=await b.newPage({viewport:{width:1500,height:1000}});
const errs=[]; page.on('pageerror',e=>errs.push(e.message)); page.on('console',m=>m.type()==='error'&&errs.push(m.text()));

// capture window.open (the GitHub path) without actually navigating
await page.addInitScript(()=>{ window.__opened=[]; const o=window.open; window.open=(u)=>{window.__opened.push(u); return {}; }; });

await page.goto(`${base}/`,{waitUntil:'networkidle'});
await page.waitForTimeout(1000);
// into the project via its card (root varies: solo=".", manifest=<dir>)
await page.locator(root ? `a.card[href*="${root}"]` : 'a.card').first().click();
await page.waitForSelector('.project-header', {timeout:15000}); await page.waitForTimeout(1200);
// open the dependency graph (label may be text or an icon+text Toc entry)
await page.locator('text=Dependency graph').first().click();
await page.waitForSelector('svg', {timeout:15000}); await page.waitForTimeout(2000);
// expand first chapter box, then click a real statement node
await page.locator('g.node').first().click();
// wait for the (worker) re-layout to add real statement nodes
let stmtIdx=-1;
for (let tries=0; tries<30 && stmtIdx<0; tries++){
  await page.waitForTimeout(400);
  const nds = page.locator('g.node');
  for (let i=0;i<await nds.count();i++){
    const nid = await nds.nth(i).getAttribute('data-nid').catch(()=>null);
    if (nid && !/^ch\d+$/.test(nid)) { stmtIdx=i; break; }
  }
}
let opened=false;
if (stmtIdx>=0){
  const n = page.locator('g.node').nth(stmtIdx);
  await n.scrollIntoViewIfNeeded().catch(()=>{});
  await n.click({force:true}); opened=true;
}
if(!opened){ console.log('NO statement node found'); await b.close(); process.exit(1); }
await page.waitForSelector('#gm-side .stmt-card',{timeout:8000}); await page.waitForTimeout(500);
await page.locator('.stmt-reviews summary').click(); await page.waitForTimeout(400);

const form = page.locator('.rv-form');
console.log(`\n== ${shot} (static=${wantStatic} repo=${wantRepo}) ==`);
const btns = await form.locator('.rv-actions .gm-btn').allInnerTexts();
console.log('buttons:', JSON.stringify(btns));
const saveIsPrimary = await form.locator('.rv-actions .gm-btn', {hasText:'Save locally'}).evaluate(el=>el.classList.contains('rv-primary'));
const ghIsPrimary   = await form.locator('.rv-actions .gm-btn', {hasText:'Send to GitHub'}).evaluate(el=>el.classList.contains('rv-primary'));
console.log('primary:', saveIsPrimary?'Save locally':ghIsPrimary?'Send to GitHub':'(none)');

// 1) validation: click Save locally with no verdict
await form.locator('.gm-btn', {hasText:'Save locally'}).click(); await page.waitForTimeout(200);
console.log('no-verdict msg:', JSON.stringify(await form.locator('.rv-err, .rv-note').innerText().catch(()=>'')));

// 2) pick a maths verdict
await form.locator('select').first().selectOption('good'); await page.waitForTimeout(150);

// 3) Save locally now
await form.locator('.gm-btn', {hasText:'Save locally'}).click(); await page.waitForTimeout(600);
console.log('save msg:', JSON.stringify(await form.locator('.rv-err, .rv-note').innerText().catch(()=>'')));

// 4) Send to GitHub
await form.locator('.gm-btn', {hasText:'Send to GitHub'}).click(); await page.waitForTimeout(400);
console.log('github msg:', JSON.stringify(await form.locator('.rv-err, .rv-note').innerText().catch(()=>'')));
const opened2 = await page.evaluate(()=>window.__opened);
console.log('github url:', opened2.length? opened2[0].split('?')[0] : '(none opened)');
if(opened2.length){ const u=new URL(opened2[0]); console.log('  title=', decodeURIComponent(u.searchParams.get('title')||'').slice(0,50)); }
await form.screenshot({path:`${OUT}/${shot}.png`}).catch(()=>{});
console.log('errors:', errs.length?errs.slice(0,2):'none');
await b.close();
