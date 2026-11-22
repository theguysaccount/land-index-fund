"""Server-side SVG line charts. The page's script adds the hover crosshair; a table always carries the values."""
import json
import math

from .fmt import esc, money, money_short

KIND_NOTE = {"census": "census", "interpolated": "estimate between censuses", "estimate": "estimate",
             "survey": "survey", "": ""}


def nice_max(v):
    """Smallest 'round' axis top at or above v, and the tick step that goes with it."""
    if v <= 0:
        return 1.0, 0.25
    mag = 10 ** math.floor(math.log10(v))
    for m, step in ((1, 0.25), (1.2, 0.3), (1.5, 0.5), (2, 0.5), (2.5, 0.5), (3, 1), (4, 1), (5, 1), (6, 2),
                    (8, 2), (10, 2.5)):
        if v <= m * mag * 1.0000001:
            return m * mag, step * mag
    return 10 * mag, 2.5 * mag


def year_ticks(first, last, marks=None):
    """Tick years: the given marks (census years) when they fit the range, else a regular step."""
    span = last - first
    if marks:
        inside = [y for y in marks if first <= y <= last]
        if len(inside) >= 3:
            return inside
    step = 1 if span <= 6 else 2 if span <= 14 else 5 if span <= 40 else 10 if span <= 90 else 25
    start = first if span <= 14 else int(math.ceil(first / float(step)) * step)
    return list(range(start, last + 1, step))


def _draw(series, label, marks, width, height, ml, mr, value_fmt, axis_fmt, unit):
    years = sorted({p[0] for s in series for p in s["points"]})
    first, last = years[0], years[-1]
    top, step = nice_max(max(p[1] for s in series for p in s["points"]))
    mt, mb = 14, 30
    pw, ph = width - ml - mr, height - mt - mb

    def x(year):
        return ml + (pw * (year - first) / float(last - first) if last > first else pw / 2.0)

    def y(value):
        return mt + ph * (1 - value / top)

    out = ['<svg class="chart" viewBox="0 0 %d %d" role="img" aria-label="%s" preserveAspectRatio="xMidYMid meet">'
           % (width, height, esc(label))]
    t = 0.0
    while t <= top * 1.0000001:
        yy = y(t)
        out.append('<line class="%s" x1="%d" x2="%d" y1="%.1f" y2="%.1f"/>' % ("base" if t == 0 else "grid", ml,
                                                                            width - mr, yy, yy))
        out.append('<text class="tick" x="%d" y="%.1f" text-anchor="end">%s</text>' % (ml - 8, yy + 4, axis_fmt(t)))
        t += step
    ticks = year_ticks(first, last, marks)
    if width < 500 and len(ticks) > 6:
        ticks = ticks[::2] if ticks[-1] in ticks[::2] else ticks[1::2]
    for yr in ticks:
        out.append('<text class="tick" x="%.1f" y="%d" text-anchor="middle">%d</text>' % (x(yr), height - 8, yr))

    ends = []
    for s in series:
        pts = s["points"]
        solid = [p for p in pts if p[2] != "estimate"]
        dashed = ([solid[-1]] if solid else []) + [p for p in pts if p[2] == "estimate"]
        cls = "s%d" % s["slot"]
        if len(solid) > 1:
            out.append('<path class="ln %s" d="M%s"/>' % (cls, "L".join("%.1f,%.1f" % (x(a), y(b)) for a, b, _ in solid)))
        if len(dashed) > 1:
            out.append('<path class="ln est %s" d="M%s"/>' % (cls, "L".join("%.1f,%.1f" % (x(a), y(b))
                                                                             for a, b, _ in dashed)))
        for a, b, kind in pts:
            if kind == "census" or len(pts) == 1:
                out.append('<circle class="mk %s" cx="%.1f" cy="%.1f" r="4"/>' % (cls, x(a), y(b)))
        ends.append((y(pts[-1][1]), x(pts[-1][0]), value_fmt(pts[-1][1])))
    placed = []
    for yy, xx, text in ends:  # a value at each line end, unless it would sit on top of another one
        if all(abs(yy - other) >= 15 for other in placed):
            out.append('<text class="end" x="%.1f" y="%.1f">%s</text>' % (xx + 8, yy + 4, esc(text)))
            placed.append(yy)
    out.append('<g class="hover" aria-hidden="true"></g></svg>')

    data = {"years": years, "x0": ml, "x1": width - mr, "y0": mt, "y1": mt + ph, "top": top, "w": width, "h": height,
            "unit": unit, "series": []}
    for s in series:
        by = {p[0]: p for p in s["points"]}
        data["series"].append({"name": s["name"], "slot": s["slot"],
                               "v": [by[yr][1] if yr in by else None for yr in years],
                               "k": [KIND_NOTE.get(by[yr][2], "") if yr in by else "" for yr in years]})
    return "".join(out), data


def line_chart(series, label, marks=None, value_fmt=money, axis_fmt=money_short, unit="per acre"):
    """An SVG line chart plus the JSON the hover layer needs, drawn twice: wide for desktop, narrow for phones
    (CSS shows one), so that axis text stays readable at both sizes.

    series: [{"name": str, "slot": 1..3, "points": [(year, value, kind)]}]  (kind: census/interpolated/estimate/'')
    Returns (html, legend_html). Estimates past the last census are dashed; census years carry a marker.
    """
    series = [s for s in series if s["points"]]
    if not series:
        return "", ""
    parts = []
    for cls, width, height, ml, mr in (("wide", 720, 330, 58, 74), ("narrow", 380, 290, 46, 60)):
        svg, data = _draw(series, label, marks, width, height, ml, mr, value_fmt, axis_fmt, unit)
        parts.append('<div class="chart-wrap %s" tabindex="0" data-chart="%s">%s<div class="tip" hidden></div></div>' % (
            cls, esc(json.dumps(data, separators=(",", ":"))), svg))

    keys = ['<li><span class="key s%d"></span>%s</li>' % (s["slot"], esc(s["name"])) for s in series]
    kinds = {p[2] for s in series for p in s["points"]}
    if "census" in kinds and len(kinds) > 1:
        keys.append('<li><span class="key dot"></span>Census year (observed)</li>')
    if "estimate" in kinds:
        keys.append('<li><span class="key dash"></span>Estimate since the last census</li>')
    legend = '<ul class="legend">%s</ul>' % "".join(keys)
    return "".join(parts), legend


def sparkline(values, width=120, height=30):
    """A tiny trend line for tables and cards. No axes: the numbers sit beside it."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        if v is None:
            continue
        pts.append("%.1f,%.1f" % (2 + (width - 4) * i / float(n - 1), 2 + (height - 4) * (1 - (v - lo) / span)))
    return ('<svg class="spark" viewBox="0 0 %d %d" width="%d" height="%d" aria-hidden="true">'
            '<path d="M%s"/></svg>') % (width, height, width, height, "L".join(pts))
