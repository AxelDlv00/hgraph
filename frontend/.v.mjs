import { chromium } from 'playwright';
const b=await chromium.launch(); const page=await b.newPage({viewport:{width:1400,height:1000}});
const errs=[]; page.on('pageerror',e=>errs.push(e.message)); page.on('console',m=>m.type()==='error'&&errs.push(m.text()));
await page.goto(process.argv[2]+'/',{waitUntil:'networkidle'}); await page.waitForTimeout(1200);
const secs=page.locator('.section');
for(let i=0;i<await secs.count();i++){
  const s=secs.nth(i);
  console.log(`§ ${await s.locator('.section-title').innerText().catch(()=>'-')}`);
  console.log(`    ${(await s.locator('> .subtitle').innerText().catch(()=>'(no subtitle)')).slice(0,62)}`);
}
console.log('overview katex:', await page.locator('.overview .katex').count(), '| errors:', errs.length?errs.slice(0,2):'none');
await b.close();
