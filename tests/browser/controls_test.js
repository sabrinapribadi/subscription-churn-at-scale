// Real-browser control audit: sliders, checkboxes, buttons, scenario presets (must match the appendix table),
// collapsible sections (click + keyboard), links that open collapsed sections, FAQ, in-page links, ids, labels.
// Run: make controls-test   (Node + Google Chrome)
const puppeteer = require("puppeteer-core"); const wait = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new" });
  const page = await b.newPage(); await page.setViewport({ width: 1280, height: 900 });
  const errs = []; page.on("pageerror", (e) => errs.push(e.message)); page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });
  await page.goto("file://" + process.argv[2], { waitUntil: "networkidle0" });
  const closed0 = await page.$$eval("details.more", (ds) => ds.map((d) => [d.querySelector("summary span").textContent, d.open]));
  // links into collapsed sections must open them (before anything else is opened)
  for (const href of ["#m-gbm", "#p4-scenarios"]) {
    await page.evaluate(() => { document.querySelectorAll("details").forEach((d) => (d.open = false)); window.scrollTo(0, 0); }); await wait(80);
    await page.click(`a[href="${href}"]`); await wait(250);
    const r = await page.evaluate((h) => { const t = document.querySelector(h), b = t.getBoundingClientRect(); return { open: !!t.closest("details") && t.closest("details").open, top: Math.round(b.top) }; }, href);
    globalThis.__linkChecks = (globalThis.__linkChecks || []).concat([[r.open && Math.abs(r.top) < 60, `link ${href} opens its collapsed section and scrolls there (top=${r.top})`]]);
  }
  await page.evaluate(() => document.querySelectorAll("details").forEach((d) => (d.open = true)));
  const snap = (sel) => page.evaluate((sel) => sel.split(",").map((s) => { const e = document.querySelector(s.trim()); return e ? e.innerHTML.length + ":" + e.textContent.slice(0, 400) : "MISSING " + s; }).join("|"), sel);
  const results = [...(globalThis.__linkChecks || [])];
  results.push([closed0.every(([, o]) => !o), `deep dives start collapsed (${closed0.map(([n]) => n).join(" · ")})`]);
  const check = async (name, sel, action) => { const before = await snap(sel); await action(); await wait(120); const after = await snap(sel); const ok = before !== after && !after.includes("MISSING"); results.push([ok, name]); };
  const setRange = (id, v) => page.evaluate((id, v) => { const e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event("input", { bubbles: true })); }, id, v);
  const ranges = { "lr-renew": [45, "#lr-out,#lr-svg,#lr-renew-o"], "pt-k": [3, "#pt-out,#pt-svg,#pt-k-o"], "pt-w": [60, "#pt-out,#pt-svg,#pt-w-o"],
    "ws-onset": [90, "#ws-out,#ws-svg,#ws-onset-o"], "ws-k": [28, "#ws-out,#ws-svg,#ws-k-o"], "oot-drift": [0.1, "#oot-out,#oot-svg,#oot-drift-o"],
    "pr-pi": [0.3, "#pr-out,#pr-svg,#pr-pi-o"], "pr-d": [2.5, "#pr-out,#pr-svg,#pr-d-o"], "gb-m": [80, "#gb-out,#gb-svg,#gb-m-o"], "gb-eta": [0.9, "#gb-out,#gb-svg,#gb-eta-o"],
    "em-noise": [1.6, "#em-out,#em-svg,#em-noise-o"], "pk-s": [0.5, "#pk-out,#pk-svg,#pk-s-o"], "pk-c": [30, "#pk-out,#pk-svg,#pk-c-o"], "pk-n": [1.2, "#pk-out,#pk-svg,#pk-n-o"],
    "bd-share": [30, "#bd-out,#bd-svg,#bd-share-o"], "pf-s": [0.35, "#pf-out,#pf-svg,#pf-s-o"], "pf-c": [60, "#pf-out,#pf-svg,#pf-c-o"] };
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
  // scenario presets: the picker must reproduce the appendix table exactly
  const grid = JSON.parse(require("fs").readFileSync(process.argv[4], "utf8")).profit_grid;
  for (const [sc, label] of [["0.1,50", "pessimistic"], ["0.2,20", "central"], ["0.3,0", "optimistic"]]) {
    await check(`preset button ${label}`, "#pf-out,#pf-svg", () => page.click(`[data-sc="${sc}"]`));
    const [sr, c] = sc.split(",").map(Number), row = grid.find((g) => g.save_rate === sr && g.contact_cost === c);
    const txt = await page.$eval("#pf-out", (e) => e.textContent), want = (row.expected_value.profit / 1e6).toFixed(1) + "M", wantLm = (row.lambdamart.profit / 1e6).toFixed(1) + "M";
    results.push([txt.includes(want) && txt.includes(wantLm), `${label} preset matches table (value order ${want}, LambdaMART ${wantLm})`]);
  }
  // summary toggles open and close a section by click and by keyboard
  await page.evaluate(() => document.querySelectorAll("details.more").forEach((d) => (d.open = false)));
  const sm = await page.$("#appendix > summary"); await sm.scrollIntoView(); await sm.click(); await wait(80);
  const opened1 = await page.$eval("#appendix", (d) => d.open); await sm.click(); await wait(80); const closed1 = await page.$eval("#appendix", (d) => !d.open);
  await page.focus("#d-methods > summary"); await page.keyboard.press("Enter"); await wait(80); const kb = await page.$eval("#d-methods", (d) => d.open);
  results.push([opened1 && closed1, "clicking a deep-dive heading opens and closes it"], [kb, "keyboard Enter opens a deep dive"]);
  await page.evaluate(() => document.querySelectorAll("details").forEach((d) => (d.open = true)));
  // FAQ details
  await page.$$eval(".faq details", (ds) => ds.forEach((d) => (d.open = false)));
  const nDetails = await page.$$eval(".faq details", (d) => d.length);
  for (let i = 0; i < nDetails; i++) { const s = await page.$$(".faq summary"); await s[i].click(); await wait(40); }
  const opened = await page.$$eval(".faq details", (d) => d.filter((x) => x.open).length); results.push([opened === nDetails, `FAQ: all ${nDetails} questions open on click`]);
  // in-page links
  const anchors = await page.$$eval('nav.toc a[href^="#"], .pipe a[href^="#"]', (as) => as.map((a) => [a.textContent.trim().slice(0, 30), a.getAttribute("href"), !!document.querySelector(a.getAttribute("href"))]));
  results.push([anchors.every((a) => a[2]), `${anchors.length} in-page links all point to existing sections`]);
  for (const [, href] of anchors) { await page.click(`a[href="${href}"]`); await wait(60); }
  const top = await page.$eval(anchors[anchors.length - 1][1], (e) => Math.round(e.getBoundingClientRect().top)); results.push([Math.abs(top) < 40, "last pipeline link scrolls to its section"]);
  const ext = await page.$$eval('a[href^="http"]', (as) => [...new Set(as.map((a) => a.href))]);
  const ids = await page.$$eval("[id]", (es) => es.map((e) => e.id)); const dup = ids.filter((x, i) => ids.indexOf(x) !== i);
  results.push([dup.length === 0, `element ids unique (${dup.join(",") || "none duplicated"})`]);
  const unlabeled = await page.$$eval("input", (is) => is.filter((i) => !i.labels || !i.labels.length).map((i) => i.id)); results.push([unlabeled.length === 0, `every input has a label (${unlabeled.join(",") || "all labelled"})`]);
  for (const [ok, name] of results) console.log(ok ? "OK  " : "FAIL", name);
  console.log(`\n${results.filter((r) => r[0]).length}/${results.length} control checks pass · JS errors: ${errs.length ? errs : "none"}`);
  require("fs").writeFileSync(process.argv[3], ext.join("\n"));
  await b.close();
})();
