import { chromium } from 'playwright';
const b=await chromium.launch(); const page=await b.newPage();
await page.goto(process.argv[2]+'/',{waitUntil:'domcontentloaded'}); await page.waitForTimeout(500);
const v = await page.evaluate(()=>window.__HGRAPH_DATA__);
console.log(`${process.argv[3]}: window.__HGRAPH_DATA__ is ${v===undefined?'undefined -> isLive=TRUE (Save primary)':'PRESENT -> isLive=false (GitHub primary)'}`);
await b.close();
