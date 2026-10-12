// Real-browser control audit: every slider, checkbox, button, tab (mouse and keyboard), FAQ, in-page link,
// unique ids and input labels on docs/index.html. Run: make controls-test   (Node + Google Chrome)
const puppeteer = require("puppeteer-core"); const wait = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new" });
  const page = await b.newPage(); await page.setViewport({ width: 1280, height: 900 });
  const errs = []; page.on("pageerror", (e) => errs.push(e.message)); page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });
  await page.goto("file://" + process.argv[2], { waitUntil: "networkidle0" });
  const snap = (sel) => page.evaluate((sel) => sel.split(",").map((s) => { const e = document.querySelector(s.trim()); return e ? e.innerHTML.length + ":" + e.textContent.slice(0, 400) : "MISSING " + s; }).join("|"), sel);
  const results = [];
  const check = async (name, sel, action) => { const before = await snap(sel); await action(); await wait(120); const after = await snap(sel); const ok = before !== after && !after.includes("MISSING"); results.push([ok, name]); };
  const setRange = (id, v) => page.evaluate((id, v) => { const e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event("input", { bubbles: true })); }, id, v);
  const ranges = { "lr-renew": [45, "#lr-out,#lr-svg,#lr-renew-o"], "pt-k": [3, "#pt-out,#pt-svg,#pt-k-o"], "pt-w": [60, "#pt-out,#pt-svg,#pt-w-o"],
    "ws-onset": [90, "#ws-out,#ws-svg,#ws-onset-o"], "ws-k": [28, "#ws-out,#ws-svg,#ws-k-o"], "oot-drift": [0.1, "#oot-out,#oot-svg,#oot-drift-o"],
    "pr-pi": [0.3, "#pr-out,#pr-svg,#pr-pi-o"], "pr-d": [2.5, "#pr-out,#pr-svg,#pr-d-o"], "gb-m": [80, "#gb-out,#gb-svg,#gb-m-o"], "gb-eta": [0.9, "#gb-out,#gb-svg,#gb-eta-o"],
    "em-noise": [1.6, "#em-out,#em-svg,#em-noise-o"], "pk-s": [0.5, "#pk-out,#pk-svg,#pk-s-o"], "pk-c": [30, "#pk-out,#pk-svg,#pk-c-o"], "pk-n": [1.2, "#pk-out,#pk-svg,#pk-n-o"],
    "bd-share": [30, "#bd-out,#bd-svg,#bd-share-o"] };
  for (const [id, [v, sel]] of Object.entries(ranges)) await check(`slider ${id}`, sel, () => setRange(id, v));
  // checkboxes (real clicks) and the dependent slider
  await check("checkbox 'No renewal at all'", "#lr-out,#lr-svg", () => page.click("#lr-none"));
  const renewDisabled = await page.$eval("#lr-renew", (e) => e.disabled); results.push([renewDisabled, "'No renewal' disables the renewal slider"]);
  await page.click("#lr-none"); await wait(80);
  const cancelDisabledBefore = await page.$eval("#lr-cancelto", (e) => e.disabled);
  await check("checkbox 'Member cancels before renewing'", "#lr-out,#lr-svg", () => page.click("#lr-cancel"));
  const cancelEnabled = await page.$eval("#lr-cancelto", (e) => !e.disabled); results.push([cancelDisabledBefore && cancelEnabled, "cancel slider enabled only when 'cancels' is ticked"]);
  await check("slider lr-cancelto (while cancel ticked)", "#lr-out,#lr-svg,#lr-cancelto-o", () => setRange("lr-cancelto", 20));
  // buttons
  await check("button Resample data", "#oot-out,#oot-svg", () => page.click("#oot-resample"));
  for (const pi of ["0.09", "0.5", "0.064"]) await check(`button churn-rate preset ${pi}`, "#pr-out,#pr-pi-o", () => page.click(`[data-pi="${pi}"]`));
  const presetValue = await page.$eval("#pr-pi", (e) => e.value); results.push([presetValue === "0.064", "preset sets the slider value (0.064)"]);
  await check("button Take one gradient step", "#lm-out,#lm-list", () => page.click("#lm-step"));
  await check("button Shuffle scores", "#lm-out,#lm-list", () => page.click("#lm-reset"));
  let ndcgUp = true; { const n0 = await page.$eval("#lm-out", (e) => parseFloat(e.textContent.match(/NDCG@5 = ([\d.]+)/)[1])); for (let i = 0; i < 6; i++) await page.click("#lm-step"); await wait(80); const n1 = await page.$eval("#lm-out", (e) => parseFloat(e.textContent.match(/NDCG@5 = ([\d.]+)/)[1])); ndcgUp = n1 >= n0; results.push([ndcgUp, `gradient steps raise NDCG@5 (${n0} → ${n1})`]); }
  // click-to-set on the budget dial
  { const el = await page.$("#bd-svg"); await el.scrollIntoView(); await wait(200); const bx = await el.boundingBox(); await page.mouse.click(bx.x + bx.width * (44 + (620 - 44) * 0.4) / 640, bx.y + bx.height * 0.5); await wait(120);
    const v = await page.$eval("#bd-share", (e) => +e.value); results.push([v >= 18 && v <= 22, `clicking the dial chart sets the dial (${v}%)`]); }
  // tabs
  await page.click("#tab-app"); await wait(80);
  const tabA = await page.evaluate(() => getComputedStyle(document.getElementById("pane-app")).display !== "none" && getComputedStyle(document.getElementById("pane-prac")).display === "none" && document.getElementById("tab-app").getAttribute("aria-selected") === "true");
  await page.click("#tab-prac"); await wait(80);
  const tabP = await page.evaluate(() => getComputedStyle(document.getElementById("pane-prac")).display !== "none" && getComputedStyle(document.getElementById("pane-app")).display === "none" && document.getElementById("tab-prac").getAttribute("aria-selected") === "true");
  results.push([tabA, "tab 'Appendix' shows appendix, hides practitioner view"], [tabP, "tab 'For practitioners' switches back"]);
  // keyboard: tabs and buttons reachable and operable
  await page.focus("#tab-app"); await page.keyboard.press("Enter"); await wait(80);
  results.push([await page.evaluate(() => getComputedStyle(document.getElementById("pane-app")).display !== "none"), "keyboard Enter on 'Appendix' tab works"]);
  await page.click("#tab-prac");
  // FAQ details
  const nDetails = await page.$$eval(".faq details", (d) => d.length);
  for (let i = 0; i < nDetails; i++) { const s = await page.$$(".faq summary"); await s[i].click(); await wait(40); }
  const opened = await page.$$eval(".faq details", (d) => d.filter((x) => x.open).length); results.push([opened === nDetails, `FAQ: all ${nDetails} questions open on click`]);
  // in-page links
  const anchors = await page.$$eval('a[href^="#"]', (as) => as.map((a) => [a.textContent.trim().slice(0, 30), a.getAttribute("href"), !!document.querySelector(a.getAttribute("href"))]));
  results.push([anchors.every((a) => a[2]), `${anchors.length} in-page links all point to existing sections`]);
  for (const [, href] of anchors.slice(0, 10)) { await page.click(`a[href="${href}"]`); await wait(60); }
  const top = await page.$eval("#m-profit", (e) => Math.round(e.getBoundingClientRect().top)); results.push([Math.abs(top) < 40, "last pipeline link scrolls to its section"]);
  const ext = await page.$$eval('a[href^="http"]', (as) => [...new Set(as.map((a) => a.href))]);
  const ids = await page.$$eval("[id]", (es) => es.map((e) => e.id)); const dup = ids.filter((x, i) => ids.indexOf(x) !== i);
  results.push([dup.length === 0, `element ids unique (${dup.join(",") || "none duplicated"})`]);
  const unlabeled = await page.$$eval("input", (is) => is.filter((i) => !i.labels || !i.labels.length).map((i) => i.id)); results.push([unlabeled.length === 0, `every input has a label (${unlabeled.join(",") || "all labelled"})`]);
  for (const [ok, name] of results) console.log(ok ? "OK  " : "FAIL", name);
  console.log(`\n${results.filter((r) => r[0]).length}/${results.length} control checks pass · JS errors: ${errs.length ? errs : "none"}`);
  require("fs").writeFileSync(process.argv[3], ext.join("\n"));
  await b.close();
})();
