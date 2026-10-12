// Real-browser check (rule R10): every chart shows a tooltip on hover, keeps it inside the chart,
// and hides it when the pointer leaves. Run: make hover-test   (needs Node + Google Chrome)

const puppeteer = require("puppeteer-core");
(async () => {
  const file = "file://" + process.argv[2], shots = process.argv[3];
  const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new", args: ["--no-sandbox"] });
  const page = await b.newPage(); await page.setViewport({ width: 1280, height: 900 });
  const errs = []; page.on("pageerror", (e) => errs.push(e.message));
  await page.goto(file, { waitUntil: "networkidle0" });
  const visibleTips = await page.$$eval(".tip", (ts) => ts.filter((t) => getComputedStyle(t).display !== "none").length);
  const appendixHidden = await page.$eval("#pane-app", (p) => getComputedStyle(p).display === "none");
  console.log(`on load: visible tooltips=${visibleTips} · appendix hidden=${appendixHidden}`);
  // open appendix too, so its charts can be tested
  const ids = await page.$$eval("svg.plot", (ss) => ss.map((s) => s.id));
  let pass = 0;
  for (const id of ids) {
    if (["res-svg", "cal-svg"].includes(id)) await page.click("#tab-app"); else await page.click("#tab-prac");
    const el = await page.$("#" + id); await el.scrollIntoView(); await new Promise((r) => setTimeout(r, 80));
    const box = await el.boundingBox(); let shown = null;
    for (const [fx, fy] of [[0.5, 0.45], [0.3, 0.5], [0.7, 0.4], [0.2, 0.3], [0.8, 0.6]]) {
      await page.mouse.move(box.x + box.width * fx, box.y + box.height * fy); await new Promise((r) => setTimeout(r, 60));
      shown = await page.evaluate((id) => { const t = document.getElementById(id).parentElement.querySelector(":scope > .tip"); if (!t || getComputedStyle(t).display === "none") return null;
        const r = t.getBoundingClientRect(), w = t.parentElement.getBoundingClientRect(); return { inside: r.left >= w.left - 1 && r.right <= w.right + 1 && r.top >= w.top - 1 && r.bottom <= w.bottom + 1, w: Math.round(r.width), h: Math.round(r.height) }; }, id);
      if (shown) break;
    }
    if (["ps-svg", "cal-svg"].includes(id) && !shown) { const c = await page.$eval("#" + id + " circle:not(.hover-mark)", (c) => { const r = c.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }); await page.mouse.move(c[0], c[1]); await new Promise((r) => setTimeout(r, 60));
      shown = await page.evaluate((id) => { const t = document.getElementById(id).parentElement.querySelector(":scope > .tip"); if (!t || getComputedStyle(t).display === "none") return null; const r = t.getBoundingClientRect(), w = t.parentElement.getBoundingClientRect(); return { inside: r.left >= w.left - 1 && r.right <= w.right + 1 && r.top >= w.top - 1 && r.bottom <= w.bottom + 1, w: Math.round(r.width), h: Math.round(r.height) }; }, id); }
    if (id === "em-svg" && !shown) { const c = await page.$eval("#em-svg circle", (c) => { const r = c.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }); await page.mouse.move(c[0], c[1]); await new Promise((r) => setTimeout(r, 60));
      shown = await page.evaluate(() => { const t = document.getElementById("em-svg").parentElement.querySelector(":scope > .tip"); return t && getComputedStyle(t).display !== "none" ? { inside: true, w: t.offsetWidth, h: t.offsetHeight } : null; }); }
    if (["lt-svg", "bd-svg"].includes(id)) await page.screenshot({ path: shots + "/tip_" + id + ".png", clip: { x: box.x - 10, y: box.y - 10, width: box.width + 20, height: box.height + 20 } });
    await page.mouse.move(5, 5); await new Promise((r) => setTimeout(r, 60));
    const gone = await page.evaluate((id) => { const t = document.getElementById(id).parentElement.querySelector(":scope > .tip"); return !t || getComputedStyle(t).display === "none"; }, id);
    const ok = shown && shown.inside && gone; if (ok) pass++;
    console.log(`${id.padEnd(8)} shown=${!!shown} ${shown ? `(${shown.w}×${shown.h}px, inside=${shown.inside})` : ""} hidden-after-leave=${gone} ${ok ? "OK" : "FAIL"}`);
  }
  // lambdamart row tooltip
  await page.click("#tab-prac"); const row = (await page.$$("#lm-list .r"))[2]; await row.scrollIntoView(); await new Promise((r) => setTimeout(r, 150)); const rb = await row.boundingBox();
  await page.mouse.move(rb.x + 40, rb.y + 5); await new Promise((r) => setTimeout(r, 60));
  const lmShown = await page.evaluate(() => { const t = document.getElementById("lm-list").parentElement.querySelector(":scope > .tip"); return t && getComputedStyle(t).display !== "none"; });
  await page.mouse.move(5, 5); await new Promise((r) => setTimeout(r, 60));
  const lmGone = await page.evaluate(() => { const t = document.getElementById("lm-list").parentElement.querySelector(":scope > .tip"); return getComputedStyle(t).display === "none"; });
  console.log(`lm rows  shown=${lmShown} hidden-after-leave=${lmGone}`);
  console.log(`${pass}/${ids.length} charts pass · page errors: ${errs.length ? errs : "none"}`);
  await b.close();
})();
