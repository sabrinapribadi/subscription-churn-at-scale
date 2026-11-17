"""Self-contained HTML/SVG charts for the churn skill (standard library only; no external scripts). Shared design with the next-site-planner skill.

Forms follow the reader's job (references/charts.md):
- paired_bars: before -> after per item (KPI baseline vs plan), baseline in grey, plan in the accent blue.
- ranked_bars: compare magnitudes, largest first; colour = category with a legend and direct labels.
- line_chart: one value over an ordered range (expected profit by share of members called), best point marked.
- diverging_bars: signed contributions around zero (reasons that raise risk in red, lower it in blue).
- stacked_bars: parts of a whole per row (where the model's extra reach over today's rule comes from).
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


def paired_bars(rows: list[dict], title: str, sub: str, foot: str, a_label: str, b_label: str, note_key: str | None = None) -> str:
    """rows: {label, a, b, note?}; a = context (grey), b = focus (blue). Sorted by b, largest first."""
    rows = sorted(rows, key=lambda r: -r["b"])
    vmax = max(max(r["a"], r["b"]) for r in rows) or 1
    lw, w, bh, gap, rh = 170, 820, 11, 2, 40
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
                out.append(f'<text x="{x + bw / 2:.1f}" y="{y + bh - 7}" text-anchor="middle" style="fill:{'var(--ink)' if var == '--ctx' else '#fff'};font-weight:600">{html.escape(unit(v))}</text>')
            x += bw
        out.append(f'<text class="val" x="{x + 8:.1f}" y="{y + bh - 6}">{html.escape(unit(sum(r["parts"])))}</text>')
    h = 8 + len(rows) * rh
    svg = (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(title)}">'
           f'<line x1="{lw}" y1="0" x2="{lw}" y2="{h}" stroke="var(--axis)"/>{"".join(out)}</svg>')
    table = ("<table><tr><th>Row</th>" + "".join(f"<th class=n>{html.escape(n)}</th>" for n, _ in segments) + "<th class=n>Total</th></tr>"
             + "".join(f"<tr><td>{html.escape(r['label'])}</td>" + "".join(f"<td class=n>{html.escape(unit(v))}</td>" for v in r["parts"])
                       + f"<td class=n>{html.escape(unit(sum(r['parts'])))}</td></tr>" for r in rows) + "</table>")
    return _page(title, sub, segments, svg, table, foot)
