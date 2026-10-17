"""Hand written SVG charts in the Task Board style.
Colours are CSS variables with a light fallback, so the same SVG follows the site's dark mode and renders on its own
(PDF, Word) in the light palette. Start of quarter is always slate grey, end of quarter is always the brand red,
and every bar carries its value as a label, so no reading depends on colour alone."""
from html import escape

FONT = "'Be Vietnam Pro', Arial, sans-serif"
MONO = "'JetBrains Mono', 'Courier New', monospace"
C = {
    "start": "var(--chart-start,#5A6873)", "end": "var(--chart-end,#EF5350)",
    "ink": "var(--chart-ink,#0c1317)", "muted": "var(--chart-muted,#4b5a64)", "grid": "var(--chart-grid,#d5dde3)",
    "s1": "var(--chart-s1,#1d3140)", "s2": "var(--chart-s2,#5A6873)", "s3": "var(--chart-s3,#a9b6bf)", "s4": "var(--chart-s4,#EF5350)",
}

def fill(c):
    return f'style="fill:{C[c]}"'

def text(x, y, s, size=12, c="ink", anchor="start", weight=400, mono=False):
    fam = MONO if mono else FONT
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{fam}" font-size="{size}" font-weight="{weight}" '
            f'text-anchor="{anchor}" {fill(c)}>{escape(s)}</text>')

def rect(x, y, w, h, c, r=2):
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0):.1f}" height="{h:.1f}" rx="{r}" {fill(c)}/>'

def svg(w, h, body, title, desc):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-labelledby="t d"><title id="t">{escape(title)}</title><desc id="d">{escape(desc)}</desc>{body}</svg>')

def legend(x, y, items):
    out, cx = [], x
    for label, c in items:
        out.append(rect(cx, y - 9, 12, 12, c, 2))
        out.append(text(cx + 18, y + 1, label, 12, "muted"))
        cx += 30 + len(label) * 6.6
    return "".join(out)

def paired_bars(rows, title, desc, fmt, width=760, label_w=230, start_label="1 July 2026", end_label="30 September 2026"):
    """rows: [(label, start, end)]. Two thin horizontal bars per row, start above end, each with its value."""
    bar, gap, row_h, top = 11, 3, 46, 38
    h = top + row_h * len(rows) + 8
    vmax = max(max(s, e) for _, s, e in rows) or 1
    plot_w = width - label_w - 120
    body = [legend(label_w, 16, [(start_label, "start"), (end_label, "end")])]
    for i, (label, s, e) in enumerate(rows):
        y = top + i * row_h
        body.append(text(label_w - 12, y + bar + 4, label, 12.5, "ink", "end"))
        for j, (v, c) in enumerate(((s, "start"), (e, "end"))):
            by = y + j * (bar + gap)
            w = plot_w * v / vmax
            body.append(rect(label_w, by, max(w, 1.5), bar, c))
            body.append(text(label_w + max(w, 1.5) + 6, by + bar - 1.5, fmt(v), 11, "muted", mono=True))
    body.append(f'<line x1="{label_w}" y1="{top - 6}" x2="{label_w}" y2="{h - 8}" style="stroke:{C["grid"]}" stroke-width="1"/>')
    return svg(width, h, "".join(body), title, desc)

def stacked_100(rows, parts, title, desc, width=760, label_w=170):
    """rows: [(label, [counts...])]; parts: [(name, colour key)]. One 100% bar per row with counts written inside or beside."""
    bar, row_h, top = 22, 50, 40
    h = top + row_h * len(rows) + 4
    plot_w = width - label_w - 20
    body = [legend(label_w, 16, parts)]
    for i, (label, vals) in enumerate(rows):
        y = top + i * row_h
        tot = sum(vals) or 1
        body.append(text(label_w - 12, y + bar / 2 + 4, label, 12.5, "ink", "end"))
        x = label_w
        for (name, c), v in zip(parts, vals):
            w = plot_w * v / tot
            if w <= 0:
                continue
            body.append(rect(x, y, w - 2 if w > 3 else w, bar, c, 2))
            if w > 28:
                light = c in ("s1", "s2", "s4")
                body.append(f'<text x="{x + w / 2 - 1:.1f}" y="{y + bar / 2 + 4:.1f}" font-family="{MONO}" font-size="11" '
                            f'text-anchor="middle" style="fill:{"#ffffff" if light else "#0c1317"}">{v:,}</text>')
            x += w
        small = [f"{name} {v:,}" for (name, _), v in zip(parts, vals) if 0 < plot_w * v / tot <= 28]
        if small:
            body.append(text(label_w, y + bar + 15, "Also: " + ", ".join(small), 10.5, "muted"))
    return svg(width, h, "".join(body), title, desc)

def dumbbell(rows, title, desc, fmt, width=760, label_w=170, vmax=None):
    """rows: [(label, start, end)] on one shared 0 to vmax axis; a dot for each date joined by a line."""
    row_h, top = 40, 44
    h = top + row_h * len(rows) + 26
    vmax = vmax or max(max(s, e) for _, s, e in rows) * 1.08
    plot_w = width - label_w - 190
    X = lambda v: label_w + plot_w * v / vmax
    body = [legend(label_w, 16, [("1 July 2026", "start"), ("30 September 2026", "end")])]
    for k in range(0, 6):
        v = vmax * k / 5
        body.append(f'<line x1="{X(v):.1f}" y1="{top - 10}" x2="{X(v):.1f}" y2="{h - 22}" style="stroke:{C["grid"]}" stroke-width="1"/>')
        body.append(text(X(v), h - 6, fmt(v), 10.5, "muted", "middle", mono=True))
    for i, (label, s, e) in enumerate(rows):
        y = top + i * row_h + 6
        body.append(text(label_w - 12, y + 4, label, 12.5, "ink", "end"))
        body.append(f'<line x1="{X(s):.1f}" y1="{y}" x2="{X(e):.1f}" y2="{y}" style="stroke:{C["muted"]}" stroke-width="2"/>')
        for v, c in ((s, "start"), (e, "end")):
            body.append(f'<circle cx="{X(v):.1f}" cy="{y}" r="6" {fill(c)} style="fill:{C[c]};stroke:var(--chart-bg,#ffffff)" stroke-width="2"/>')
        lo, hi = (s, e) if s <= e else (e, s)
        lab = f"{fmt(s)} to {fmt(e)}" if fmt(s) != fmt(e) else f"{fmt(e)} on both dates"
        body.append(text(X(hi) + 12, y + 4, lab, 11, "muted", mono=True))
    return svg(width, h, "".join(body), title, desc)

def flow_bars(rows, title, desc, fmt, width=760, label_w=200, left="RBNT sent out", right="RBNT received"):
    """rows: [(label, in, out)]. A diverging bar per row: out to the left, in to the right of a shared zero line."""
    bar, row_h, top = 14, 34, 40
    h = top + row_h * len(rows) + 6
    vmax = max(max(i, o) for _, i, o in rows) or 1
    half = (width - label_w - 130) / 2
    zero = label_w + 60 + half
    one_sided = right is None
    if one_sided:                                   # only outflows: bars run left to right from the label column
        half = width - label_w - 90
        zero = label_w
    body = [legend(label_w, 16, [(left, "start")] + ([] if one_sided else [(right, "end")]))]
    body.append(f'<line x1="{zero}" y1="{top - 8}" x2="{zero}" y2="{h - 4}" style="stroke:{C["grid"]}" stroke-width="1"/>')
    for k, (label, vin, vout) in enumerate(rows):
        y = top + k * row_h
        body.append(text(label_w - 12, y + bar - 2, label, 12.5, "ink", "end"))
        wo, wi = half * vout / vmax, half * vin / vmax
        if vout and one_sided:
            body.append(rect(zero, y, max(wo, 1.5), bar, "start"))
            body.append(text(zero + max(wo, 1.5) + 6, y + bar - 3, fmt(vout), 10.5, "muted", mono=True))
        elif vout:
            body.append(rect(zero - max(wo, 1.5), y, max(wo, 1.5), bar, "start"))
            body.append(text(zero - max(wo, 1.5) - 6, y + bar - 3, fmt(vout), 10.5, "muted", "end", mono=True))
        if vin:
            body.append(rect(zero, y, max(wi, 1.5), bar, "end"))
            body.append(text(zero + max(wi, 1.5) + 6, y + bar - 3, fmt(vin), 10.5, "muted", mono=True))
        if not vin and not vout:
            body.append(text(zero + 8, y + bar - 3, "no transfers", 10.5, "muted"))
    return svg(width, h, "".join(body), title, desc)

def big(v):
    """RBNT amounts for chart labels: 1.23B, 45.6M, 7.8K."""
    a = abs(v)
    if a >= 1e9:
        return f"{v / 1e9:.2f}B"
    if a >= 1e6:
        return f"{v / 1e6:.1f}M"
    if a >= 1e3:
        return f"{v / 1e3:.1f}K"
    return f"{v:,.0f}"
