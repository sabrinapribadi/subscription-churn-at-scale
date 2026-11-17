"""Self-contained HTML/SVG charts for the churn skill (standard library only; no external scripts). Shared design with the next-site-planner skill.

Forms follow the reader's job (references/charts.md):
- paired_bars: before -> after per item (KPI baseline vs plan), baseline in grey, plan in the accent blue.
- ranked_bars: compare magnitudes, largest first; colour = category with a legend and direct labels.
- line_chart: one value over an ordered range (expected profit by share of members called), best point marked.
- diverging_bars: signed contributions around zero (reasons that raise risk in red, lower it in blue).
- stacked_bars: parts of a whole per row (where the model's extra reach over today's rule comes from).
- confidence_page: where each view says to stop (dot plot), a pilot-size simulation (slider) and the decision after the pilot (flow).
Palette: validated reference palette (blue, orange, aqua for categories; grey for context), light and dark themes.
Every bar has a hover/focus tooltip, values are printed (aqua is under 3:1 on light, so labels are required),
and a table view sits under the chart.
"""
from __future__ import annotations

import html

CSS = """
:root{--surface:#fcfcfb;--page:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
--c1:#2a78d6;--c2:#eb6834;--c3:#1baf7a;--ctx:#c3c2b7;--pos:#e34948;--neg:#2a78d6;--ring:rgba(11,11,11,.10);color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--surface:#1a1a19;--page:#0d0d0d;--ink:#f0efec;--ink2:#c3c2b7;
--muted:#898781;--grid:#2c2c2a;--axis:#383835;--c1:#3987e5;--c2:#d95926;--c3:#199e70;--ctx:#52514e;--pos:#e66767;--neg:#3987e5;--ring:rgba(255,255,255,.10);color-scheme:dark}}
:root[data-theme=dark]{--surface:#1a1a19;--page:#0d0d0d;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;
--c1:#3987e5;--c2:#d95926;--c3:#199e70;--ctx:#52514e;--pos:#e66767;--neg:#3987e5;--ring:rgba(255,255,255,.10);color-scheme:dark}
body{margin:0;background:var(--page);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
.card{max-width:860px;margin:16px auto;padding:18px 20px;background:var(--surface);border:1px solid var(--ring);border-radius:10px}
h1{font-size:18px;margin:0 0 4px;text-wrap:balance}.sub{color:var(--ink2);margin:0 0 12px}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:var(--ink2);margin:0 0 6px}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
svg{width:100%;height:auto;display:block}svg text{fill:var(--ink2);font-size:12px}svg .val{fill:var(--ink);font-variant-numeric:tabular-nums}
svg .lab{fill:var(--ink)}svg rect.bar{cursor:default;outline:none}svg rect.bar:focus,svg rect.bar:hover{stroke:var(--ink);stroke-width:1.5}
.tip{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--ring);border-radius:6px;
padding:6px 8px;font-size:12.5px;box-shadow:0 2px 8px rgba(0,0,0,.12);display:none;max-width:280px}
details{margin-top:10px;font-size:13px}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:4px 8px;border-bottom:1px solid var(--grid);text-align:left}td.n,th.n{text-align:right}
.foot{color:var(--muted);font-size:12px;margin-top:10px}
"""

JS = """<script>
const tip=document.querySelector('.tip');
function show(e,t){tip.innerHTML=t;tip.style.display='block';const r=e.target.getBoundingClientRect();
tip.style.left=Math.min(window.innerWidth-290,(e.clientX||r.right)+12)+'px';tip.style.top=((e.clientY||r.top)+12)+'px';}
document.querySelectorAll('rect.bar').forEach(b=>{const t=b.dataset.tip;
b.addEventListener('mousemove',e=>show(e,t));b.addEventListener('focus',e=>show(e,t));
['mouseleave','blur'].forEach(ev=>b.addEventListener(ev,()=>tip.style.display='none'));});
</script>"""


def _fmt(v: float) -> str:
    return f"{v:,.0f}"


def _page(title: str, sub: str, legend: list[tuple[str, str]], svg: str, table: str, foot: str) -> str:
    leg = "".join(f'<span><span class="sw" style="background:var({c})"></span>{html.escape(n)}</span>' for n, c in legend)
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body><div class=\"card\"><h1>{html.escape(title)}</h1>"
            f'<p class="sub">{html.escape(sub)}</p>{f"<div class=legend>{leg}</div>" if legend else ""}{svg}'
            f"<details><summary>Table view</summary>{table}</details><p class=\"foot\">{html.escape(foot)}</p></div>"
            f'<div class="tip" role="tooltip"></div>{JS}</body></html>')


def paired_bars(rows: list[dict], title: str, sub: str, foot: str, a_label: str, b_label: str, note_key: str | None = None, label_width: int = 170) -> str:
    """rows: {label, a, b, note?}; a = context (grey), b = focus (blue). Sorted by b, largest first."""
    rows = sorted(rows, key=lambda r: -r["b"])
    vmax = max(max(r["a"], r["b"]) for r in rows) or 1
    lw, w, bh, gap, rh = label_width, 820, 11, 2, 40
    plot = w - lw - 130
    y0 = 6
    parts = []
    for i, r in enumerate(rows):
        y = y0 + i * rh
        parts.append(f'<text class="lab" x="{lw - 10}" y="{y + bh + 4}" text-anchor="end">{html.escape(r["label"])}</text>')
        for k, (key, var, name) in enumerate((("a", "--ctx", a_label), ("b", "--c1", b_label))):
            v = r[key]; bw = max(2, plot * v / vmax); yy = y + k * (bh + gap)
            tipt = html.escape(f"<b>{r['label']}</b><br>{name}: about {_fmt(v)}" + (f"<br>{r['note']}" if r.get("note") else ""), quote=True)
            parts.append(f'<rect class="bar" tabindex="0" x="{lw}" y="{yy}" width="{bw:.1f}" height="{bh}" rx="3" fill="var({var})" data-tip="{tipt}"/>')
            if key == "b":
                txt = f"{_fmt(v)}" + (f"  ·  {r['note']}" if r.get("note") else "")
                parts.append(f'<text class="val" x="{lw + bw + 6:.1f}" y="{yy + bh - 1}">{html.escape(txt)}</text>')
            else:
                parts.append(f'<text x="{lw + bw + 6:.1f}" y="{yy + bh - 1}">{_fmt(v)}</text>')
    h = y0 + len(rows) * rh
    svg = (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(title)}">'
           f'<line x1="{lw}" y1="0" x2="{lw}" y2="{h}" stroke="var(--axis)"/>{"".join(parts)}</svg>')
    table = ("<table><tr><th>Item</th><th class=n>" + html.escape(a_label) + "</th><th class=n>" + html.escape(b_label) + "</th><th>Note</th></tr>"
             + "".join(f"<tr><td>{html.escape(r['label'])}</td><td class=n>{_fmt(r['a'])}</td><td class=n>{_fmt(r['b'])}</td>"
                       f"<td>{html.escape(r.get('note') or '')}</td></tr>" for r in rows) + "</table>")
    return _page(title, sub, [(a_label, "--ctx"), (b_label, "--c1")], svg, table, foot)


def ranked_bars(rows: list[dict], title: str, sub: str, foot: str, categories: list[str]) -> str:
    """rows: {label, v, cat, note?, tip?}; colour by category (max 3, fixed order), largest first."""
    order = {c: f"--c{i + 1}" for i, c in enumerate(categories[:3])}
    rows = sorted(rows, key=lambda r: -r["v"])
    vmax = max(r["v"] for r in rows) or 1
    lw, w, bh, rh = 250, 820, 16, 30
    plot = w - lw - 170
    parts = []
    for i, r in enumerate(rows):
        y = 6 + i * rh; bw = max(2, plot * r["v"] / vmax)
        tipt = html.escape(f"<b>{r['label']}</b><br>{r.get('tip', '')}", quote=True)
        parts.append(f'<text class="lab" x="{lw - 10}" y="{y + bh - 3}" text-anchor="end">{html.escape(r["label"])}</text>')
        parts.append(f'<rect class="bar" tabindex="0" x="{lw}" y="{y}" width="{bw:.1f}" height="{bh}" rx="3" fill="var({order[r["cat"]]})" data-tip="{tipt}"/>')
        label = r.get("text") or (_fmt(r["v"]) + ("  ·  " + r["note"] if r.get("note") else ""))   # "text" overrides, e.g. money in millions
        parts.append(f'<text class="val" x="{lw + bw + 6:.1f}" y="{y + bh - 3}">{html.escape(label)}</text>')
    h = 6 + len(rows) * rh
    svg = (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(title)}">'
           f'<line x1="{lw}" y1="0" x2="{lw}" y2="{h}" stroke="var(--axis)"/>{"".join(parts)}</svg>')
    table = ("<table><tr><th>Item</th><th>Category</th><th class=n>Value</th><th>Note</th></tr>"
             + "".join(f"<tr><td>{html.escape(r['label'])}</td><td>{html.escape(r['cat'])}</td><td class=n>{_fmt(r['v'])}</td>"
                       f"<td>{html.escape(r.get('note') or '')}</td></tr>" for r in rows) + "</table>")
    legend = [(c, order[c]) for c in categories[:3] if any(r["cat"] == c for r in rows)]
    return _page(title, sub, legend, svg, table, foot)


def line_chart(points: list[tuple[float, float]], title: str, sub: str, foot: str, x_label: str, y_label: str,
               x_fmt=lambda x: f"{x:.0%}", y_fmt=lambda y: f"{y:,.0f}", mark: tuple[float, float] | None = None, mark_label: str = "") -> str:
    """One series over an ordered x; hover points; the marked point (e.g. the best share) is labelled."""
    w, h, l, r, t, b = 820, 320, 90, 30, 16, 46
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    x0, x1 = min(xs), max(xs); y0, y1 = min(0.0, min(ys)), max(ys) * 1.08 or 1
    X = lambda x: l + (w - l - r) * (x - x0) / ((x1 - x0) or 1)
    Y = lambda y: t + (h - t - b) * (1 - (y - y0) / ((y1 - y0) or 1))
    ticks = [y0 + (y1 - y0) * i / 4 for i in range(5)]
    grid = "".join(f'<line x1="{l}" y1="{Y(v):.1f}" x2="{w - r}" y2="{Y(v):.1f}" stroke="var(--grid)"/>'
                   f'<text x="{l - 8}" y="{Y(v) + 4:.1f}" text-anchor="end">{html.escape(y_fmt(v))}</text>' for v in ticks)
    xt = [points[i][0] for i in range(0, len(points), max(1, len(points) // 6))]
    xticks = "".join(f'<text x="{X(v):.1f}" y="{h - b + 18}" text-anchor="middle">{html.escape(x_fmt(v))}</text>' for v in xt)
    path = "M" + " L".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in points)
    dots = "".join(f'<rect class="bar" tabindex="0" x="{X(x) - 6:.1f}" y="{Y(y) - 6:.1f}" width="12" height="12" rx="6" fill="var(--c1)" fill-opacity="0.001" '
                   f'data-tip="{html.escape(f"{x_label}: {x_fmt(x)}<br>{y_label}: {y_fmt(y)}", quote=True)}"/>' for x, y in points)
    mk = ""
    if mark:
        mk = (f'<circle cx="{X(mark[0]):.1f}" cy="{Y(mark[1]):.1f}" r="6" fill="var(--c1)" stroke="var(--surface)" stroke-width="2"/>'
              f'<text class="val" x="{X(mark[0]) + 10:.1f}" y="{Y(mark[1]) - 10:.1f}">{html.escape(mark_label)}</text>')
    svg = (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(title)}">{grid}'
           f'<line x1="{l}" y1="{Y(0):.1f}" x2="{w - r}" y2="{Y(0):.1f}" stroke="var(--axis)"/>{xticks}'
           f'<text x="{(l + w - r) / 2}" y="{h - 6}" text-anchor="middle">{html.escape(x_label)}</text>'
           f'<path d="{path}" fill="none" stroke="var(--c1)" stroke-width="2"/>{mk}{dots}</svg>')
    table = ("<table><tr><th>" + html.escape(x_label) + "</th><th class=n>" + html.escape(y_label) + "</th></tr>"
             + "".join(f"<tr><td>{html.escape(x_fmt(x))}</td><td class=n>{html.escape(y_fmt(y))}</td></tr>" for x, y in points) + "</table>")
    return _page(title, sub, [], svg, table, foot)


def diverging_bars(rows: list[dict], title: str, sub: str, foot: str, pos_label: str, neg_label: str) -> str:
    """rows: {label, v (signed), note?}; positive = red to the right, negative = blue to the left, largest |v| first."""
    rows = sorted(rows, key=lambda r: -abs(r["v"]))
    vmax = max(abs(r["v"]) for r in rows) or 1
    lw, w, bh, rh = 230, 820, 16, 30
    mid = lw + (w - lw - 40) / 2; half = (w - lw - 40) / 2 - 60
    parts = []
    for i, r in enumerate(rows):
        y = 6 + i * rh; bw = max(2, half * abs(r["v"]) / vmax); pos = r["v"] >= 0
        x = mid if pos else mid - bw
        tipt = html.escape(f"<b>{r['label']}</b><br>{r.get('note', '')}<br>{pos_label if pos else neg_label} ({r['v']:+.2f})", quote=True)
        parts.append(f'<text class="lab" x="{lw - 10}" y="{y + bh - 3}" text-anchor="end">{html.escape(r["label"])}</text>')
        parts.append(f'<rect class="bar" tabindex="0" x="{x:.1f}" y="{y}" width="{bw:.1f}" height="{bh}" rx="3" fill="var({"--pos" if pos else "--neg"})" data-tip="{tipt}"/>')
        tx = (x + bw + 6) if pos else (x - 6)
        parts.append(f'<text class="val" x="{tx:.1f}" y="{y + bh - 3}" text-anchor="{"start" if pos else "end"}">{html.escape(r.get("note", ""))}</text>')
    h = 6 + len(rows) * rh
    svg = (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(title)}">'
           f'<line x1="{mid:.1f}" y1="0" x2="{mid:.1f}" y2="{h}" stroke="var(--axis)"/>{"".join(parts)}</svg>')
    table = ("<table><tr><th>Reason</th><th>Value</th><th class=n>Contribution</th></tr>"
             + "".join(f"<tr><td>{html.escape(r['label'])}</td><td>{html.escape(r.get('note', ''))}</td><td class=n>{r['v']:+.2f}</td></tr>" for r in rows) + "</table>")
    return _page(title, sub, [(pos_label, "--pos"), (neg_label, "--neg")], svg, table, foot)


def stacked_bars(rows: list[dict], title: str, sub: str, foot: str, segments: list[tuple[str, str]], unit=lambda v: f"{v:.1f}") -> str:
    """rows: {label, parts: [values in the order of `segments`]}; segments: (name, css var). Total printed at the end of each bar."""
    vmax = max(sum(r["parts"]) for r in rows) or 1
    lw, w, bh, rh = 190, 820, 22, 40
    plot = w - lw - 110
    out = []
    for i, r in enumerate(rows):
        y, x = 8 + i * rh, lw
        out.append(f'<text class="lab" x="{lw - 10}" y="{y + bh - 6}" text-anchor="end">{html.escape(r["label"])}</text>')
        for (name, var), v in zip(segments, r["parts"]):
            if v <= 0:
                continue
            bw = plot * v / vmax
            tipt = html.escape(f"<b>{r['label']}</b><br>{name}: {unit(v)}", quote=True)
            out.append(f'<rect class="bar" tabindex="0" x="{x:.1f}" y="{y}" width="{max(bw - 2, 1):.1f}" height="{bh}" rx="3" fill="var({var})" data-tip="{tipt}"/>')
            if bw > 46:
                ink = "var(--ink)" if var == "--ctx" else "#fff"                     # dark text on the grey segment
                out.append(f'<text x="{x + bw / 2:.1f}" y="{y + bh - 7}" text-anchor="middle" style="fill:{ink};font-weight:600">{html.escape(unit(v))}</text>')
            x += bw
        out.append(f'<text class="val" x="{x + 8:.1f}" y="{y + bh - 6}">{html.escape(unit(sum(r["parts"])))}</text>')
    h = 8 + len(rows) * rh
    svg = (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(title)}">'
           f'<line x1="{lw}" y1="0" x2="{lw}" y2="{h}" stroke="var(--axis)"/>{"".join(out)}</svg>')
    table = ("<table><tr><th>Row</th>" + "".join(f"<th class=n>{html.escape(n)}</th>" for n, _ in segments) + "<th class=n>Total</th></tr>"
             + "".join(f"<tr><td>{html.escape(r['label'])}</td>" + "".join(f"<td class=n>{html.escape(unit(v))}</td>" for v in r["parts"])
                       + f"<td class=n>{html.escape(unit(sum(r['parts'])))}</td></tr>" for r in rows) + "</table>")
    return _page(title, sub, segments, svg, table, foot)


def _m(v: float) -> str:
    return f"NT${v / 1e6:.1f}M" if abs(v) >= 1e6 else f"NT${v:,.0f}"


def confidence_page(c: dict, foot: str) -> str:
    """Three parts: dot plot of each view's best share against the user's capacity; pilot slider; decision flow."""
    import json as _json
    save, share, cost = c["save_rate"], c["share"], c["cost_per_call"]
    views = [("half_save_rate", f"Half your save rate ({save / 2:.1%})"), ("forecast", f"Forecast ({save:.0%} save rate)"),
             ("backtest", f"Backtest, March 2017 ({save:.0%})")]
    lo, hi = c["range_share"]
    stops = ", ".join("{:.0%}".format(c["best_share"][k]) for k, _ in views)          # no nested quotes: Python 3.8+
    n_more = c["views_say_call_more"]
    agree = "All three checks" if n_more == c["views"] else f"{n_more} of our {c['views']} checks"
    title = f"{agree} say calling more than {share:.1%} pays; they stop at {stops}"
    sub = (f"The three checks: our forecast, the same forecast at half your save rate, and what actually happened to March 2017 members. "
           f"Even at half your save rate your {c['members_called']:,} calls earn {_m(c['profit_at_half_save_rate'])}; "
           f"the break-even save rate is {c['break_even_save_rate']:.1%}. The open question is where to stop: a {c['spread_points']}-point spread.")
    # 1. dot plot
    w, lw, rw, rh, top = 820, 220, 150, 44, 34
    xmax = max(0.4, hi + 0.06)
    X = lambda v: lw + (w - lw - rw) * v / xmax
    h = top + rh * len(views) + 28
    parts = [f'<rect x="{X(lo):.1f}" y="{top - 8}" width="{X(hi) - X(lo):.1f}" height="{rh * len(views)}" fill="var(--c1)" fill-opacity="0.10" rx="4"/>',
             f'<text x="{(X(lo) + X(hi)) / 2:.1f}" y="{top - 14}" text-anchor="middle">where to stop is uncertain: {lo:.0%}–{hi:.0%}</text>']
    for i, (k, name) in enumerate(views):
        y = top + i * rh + rh / 2 - 4
        b, prof = c["best_share"][k], c["best_profit"][k]
        tipt = html.escape(f"<b>{name}</b><br>Best share {b:.0%} (about {c['best_members'][k]:,} calls)<br>Expected profit there {_m(prof)}", quote=True)
        parts += [f'<text class="lab" x="{lw - 12}" y="{y + 4}" text-anchor="end">{html.escape(name)}</text>',
                  f'<line x1="{lw}" y1="{y}" x2="{w - rw}" y2="{y}" stroke="var(--grid)"/>',
                  f'<rect class="bar" tabindex="0" x="{X(b) - 7:.1f}" y="{y - 7}" width="14" height="14" rx="7" fill="var(--c1)" stroke="var(--surface)" stroke-width="2" data-tip="{tipt}"/>',
                  f'<text class="val" x="{X(b) + 12:.1f}" y="{y + 4}">stop at {b:.0%} · {html.escape(_m(prof))}</text>']
    yb = top + rh * len(views) - 6
    parts += [f'<line x1="{X(share):.1f}" y1="{top - 8}" x2="{X(share):.1f}" y2="{yb}" stroke="var(--c2)" stroke-width="2" stroke-dasharray="5 4"/>',
              f'<text x="{X(share) + 4:.1f}" y="{yb + 14}" style="fill:var(--c2);font-weight:600">you: {share:.1%}</text>',
              f'<line x1="{lw}" y1="{yb}" x2="{w - rw}" y2="{yb}" stroke="var(--axis)"/>']
    for v in [i / 10 for i in range(int(xmax * 10) + 1)]:
        parts.append(f'<text x="{X(v):.1f}" y="{h - 2}" text-anchor="middle">{v:.0%}</text>')
    dots = f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Best share by view">{"".join(parts)}</svg>'
    # 2. pilot simulation (numbers computed in the page from these inputs)
    f = c["floor"]
    data = {"save": save, "cost": cost, "precision": c["pilot"]["precision_forecast"], "ev": f["expected_value_at_risk"], "k": f["members_called"],
            "floor_share": f["share"]}
    pilot = (f'<h2>Pilot simulation: how many test calls before scaling?</h2>'
             f'<p class="sub">Move the slider. A bigger pilot measures the save rate more tightly, so the profit range at the floor '
             f'({f["members_called"]:,} calls, {f["share"]:.0%}) narrows.</p>'
             f'<label class="sl">Pilot calls <input id="pc" type="range" min="100" max="1000" step="100" value="{c["pilot"]["calls"]}" aria-label="Pilot calls">'
             f'<b id="pv"></b></label><div class="kpis" id="out"></div>'
             f'<svg id="mg" viewBox="0 0 820 170" role="img" aria-label="Save-rate margin by pilot size"></svg>')
    # 3. decision flow
    fl = c["best_members"]
    flow = (f'<h2>After the pilot: the decision</h2><div class="flow">'
            f'<div class="box"><b>Pilot</b><br>{c["pilot"]["calls"]} calls · about {_m(c["pilot"]["calls"] * cost)}</div><div class="arr">→</div>'
            f'<div class="box"><b>Measure</b><br>share of called churners kept</div><div class="arr">→</div><div class="outs">'
            f'<div class="out"><b>{save:.0%} or more</b>: scale toward {fl["forecast"]:,}–{fl["backtest"]:,} calls</div>'
            f'<div class="out"><b>{save / 2:.1%}–{save:.0%}</b>: call up to the floor, {f["members_called"]:,}</div>'
            f'<div class="out"><b>{c["break_even_save_rate"]:.1%}–{save / 2:.1%}</b>: keep your {c["members_called"]:,} calls; add no capacity</div>'
            f'<div class="out"><b>below {c["break_even_save_rate"]:.1%}</b>: stop; calls cost more than they keep</div></div></div>')
    table = ("<table><tr><th>View</th><th class=n>Best share</th><th class=n>Calls</th><th class=n>Expected profit</th></tr>"
             + "".join(f"<tr><td>{html.escape(n)}</td><td class=n>{c['best_share'][k]:.0%}</td><td class=n>{c['best_members'][k]:,}</td>"
                       f"<td class=n>{html.escape(_m(c['best_profit'][k]))}</td></tr>" for k, n in views) + "</table>")
    extra_css = (".card h2{font-size:15px;margin:22px 0 4px}.sl{display:flex;gap:12px;align-items:center;margin:8px 0}.sl input{flex:1;max-width:420px}"
                 ".kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:8px 0}"
                 ".kpi{border:1px solid var(--ring);border-radius:8px;padding:8px 10px}.kpi b{display:block;font-size:18px;font-variant-numeric:tabular-nums}"
                 ".kpi span{color:var(--ink2);font-size:12px}.flow{display:flex;flex-wrap:wrap;gap:8px;align-items:center}"
                 ".box,.out{border:1px solid var(--ring);border-radius:8px;padding:8px 10px;background:var(--page)}.box{min-width:150px}"
                 ".outs{display:grid;gap:6px;flex:1;min-width:260px}.arr{color:var(--muted);font-size:18px}")
    js = """<script>
const D=__DATA__;const pc=document.getElementById('pc'),pv=document.getElementById('pv'),out=document.getElementById('out'),mg=document.getElementById('mg');
const M=n=>1.96*Math.sqrt(D.save*(1-D.save)/(n*D.precision));const fm=v=>Math.abs(v)>=1e6?'NT$'+(v/1e6).toFixed(1)+'M':'NT$'+Math.round(v).toLocaleString('en-US');
const X=n=>80+(800-80-20)*(n-100)/900,Y=m=>14+(170-14-36)*(1-m/0.14);
let g='';for(let m=0;m<=0.14;m+=0.02){g+=`<line x1="80" y1="${Y(m)}" x2="800" y2="${Y(m)}" stroke="var(--grid)"/><text x="72" y="${Y(m)+4}" text-anchor="end">±${Math.round(m*100)} pts</text>`;}
for(let n=100;n<=1000;n+=100){g+=`<text x="${X(n)}" y="160" text-anchor="middle">${n}</text>`;}
let path='';for(let n=100;n<=1000;n+=20){path+=(path?' L':'M')+X(n).toFixed(1)+','+Y(M(n)).toFixed(1);}
g+=`<path d="${path}" fill="none" stroke="var(--c1)" stroke-width="2"/><circle id="dot" r="6" fill="var(--c2)" stroke="var(--surface)" stroke-width="2"/>`;
mg.innerHTML=g;
function upd(){const n=+pc.value,m=M(n),lo=Math.max(0,D.save-m),hi=D.save+m;pv.textContent=n+' calls';
 const p=s=>s*D.ev-D.cost*D.k;
 out.innerHTML=`<div class="kpi"><span>Churners reached in the pilot</span><b>about ${Math.round(n*D.precision)}</b></div>`+
 `<div class="kpi"><span>Save rate measured within (95%)</span><b>±${(m*100).toFixed(1)} pts</b></div>`+
 `<div class="kpi"><span>Save rate range</span><b>${(lo*100).toFixed(1)}–${(hi*100).toFixed(1)}%</b></div>`+
 `<div class="kpi"><span>Profit at the floor</span><b>${fm(p(lo))} to ${fm(p(hi))}</b></div>`+
 `<div class="kpi"><span>Pilot cost</span><b>${fm(n*D.cost)}</b></div>`;
 const d=document.getElementById('dot');d.setAttribute('cx',X(n));d.setAttribute('cy',Y(m));}
pc.addEventListener('input',upd);upd();
</script>""".replace("__DATA__", _json.dumps(data))
    page = _page(title, sub, [], dots + pilot + flow, table + "<p>Pilot math: churners reached = calls × the forecast share of called members who churn "
                 f"({c['pilot']['precision_forecast']:.0%}, conservative); margin = 1.96 × √(r(1 − r) / churners).</p>", foot)
    return page.replace("</style>", extra_css + "</style>", 1).replace("</body>", js + "</body>", 1)
