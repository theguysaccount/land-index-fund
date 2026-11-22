"""Choropleth maps as plain SVG: one national file (linked counties, no script) and an inline map per state.

Colour is one blue ramp, light to dark, in at most seven classes. In dark mode the ramp runs the other way, so
the low end still recedes toward the surface. Counties without a value are a neutral grey.
"""
from .fmt import esc, money

RAMP = {  # step -> hex, from the documented sequential ramp
    100: "#cde2fb", 150: "#b7d3f6", 200: "#9ec5f4", 250: "#86b6ef", 300: "#6da7ec", 350: "#5598e7", 400: "#3987e5",
    450: "#2a78d6", 500: "#256abf", 550: "#1c5cab", 600: "#184f95", 650: "#104281", 700: "#0d366b"}
STEPS = {1: [450], 2: [250, 550], 3: [200, 450, 650], 4: [150, 350, 500, 650], 5: [150, 300, 450, 550, 700],
         6: [100, 250, 350, 450, 550, 700], 7: [100, 200, 300, 400, 500, 600, 700]}
NO_DATA = ("#e1e0d9", "#2c2c2a")
SURFACE = ("#fcfcfb", "#1a1a19")


def colours(classes):
    light = [RAMP[s] for s in STEPS[classes]]
    return light, list(reversed(light))


def nice_break(v):
    step = 50 if v < 1000 else 100 if v < 2500 else 250 if v < 5000 else 500 if v < 10000 else 1000 if v < 50000 else 5000
    return int(round(v / float(step)) * step)


def breaks(values, classes):
    """Cut points that put about the same number of counties in each class, rounded to readable numbers."""
    vals = sorted(v for v in values if v is not None)
    if len(vals) < 2:
        return []
    classes = max(1, min(classes, len(set(vals))))
    cuts = []
    for i in range(1, classes):
        b = nice_break(vals[min(len(vals) - 1, int(len(vals) * i / float(classes)))])
        if b > vals[0] and b <= vals[-1] and (not cuts or b > cuts[-1]):
            cuts.append(b)
    return cuts


def klass(value, cuts):
    return sum(1 for b in cuts if value >= b)


def legend_labels(cuts):
    if not cuts:
        return ["All counties"]
    labels = ["Under %s" % money(cuts[0])]
    for a, b in zip(cuts, cuts[1:]):
        labels.append("%s to %s" % (money(a), money(b)))
    labels.append("%s or more" % money(cuts[-1]))
    return labels


def path_d(rings):
    parts = []
    for r in rings:
        seg = ["M%d %d" % (r[0], r[1])]
        seg.append("l" + " ".join("%d %d" % (r[i], r[i + 1]) for i in range(2, len(r), 2)))
        parts.append("".join(seg) + "z")
    return "".join(parts)


def bbox(shapes):
    xs, ys = [], []
    for rings in shapes:
        for r in rings:
            px, py = r[0], r[1]
            xs.append(px)
            ys.append(py)
            for i in range(2, len(r), 2):
                px += r[i]
                py += r[i + 1]
                xs.append(px)
                ys.append(py)
    return min(xs), min(ys), max(xs), max(ys)


def legend_html(cuts, title, note_no_data=True):
    labels = legend_labels(cuts)
    items = ['<li><span class="sw q%d-%d"></span>%s</li>' % (len(labels), i, esc(t)) for i, t in enumerate(labels)]
    if note_no_data:
        items.append('<li><span class="sw nodata"></span>No published value</li>')
    return '<div class="map-legend"><p>%s</p><ul>%s</ul></div>' % (esc(title), "".join(items))


def legend_css():
    """Swatch and fill classes for every class count, light and dark. Shared by pages and inline state maps."""
    light, dark = [], []
    for n in sorted(STEPS):
        lt, dk = colours(n)
        for i in range(n):
            light.append(".q%d-%d{background:%s;fill:%s}" % (n, i, lt[i], lt[i]))
            dark.append(".q%d-%d{background:%s;fill:%s}" % (n, i, dk[i], dk[i]))
    light.append(".nodata{background:%s;fill:%s}" % (NO_DATA[0], NO_DATA[0]))
    dark.append(".nodata{background:%s;fill:%s}" % (NO_DATA[1], NO_DATA[1]))
    return "".join(light) + "@media (prefers-color-scheme:dark){" + "".join(dark) + "}"


def us_map_svg(geo, geo_states, values, links, titles, cuts):
    """The national county map as a standalone SVG document.

    values/links/titles: {fips: ...}. Links open in the top window, because the file is embedded with <object>.
    Links carry tabindex=-1: three thousand tab stops would bury the page for keyboard users, who have the
    county finder and the state list instead.
    """
    n = len(cuts) + 1
    lt, dk = colours(n)
    css = ["path{stroke:%s;stroke-width:.5;vector-effect:non-scaling-stroke}" % SURFACE[0],
           ".st{fill:none;stroke:%s;stroke-width:1.4;pointer-events:none}" % SURFACE[0],
           ".nd{fill:%s}" % NO_DATA[0], "a:hover path,a:focus path{stroke:#0b0b0b;stroke-width:1.5}"]
    css += [".b%d{fill:%s}" % (i, c) for i, c in enumerate(lt)]
    dark = ["path{stroke:%s}" % SURFACE[1], ".st{stroke:%s}" % SURFACE[1], ".nd{fill:%s}" % NO_DATA[1],
            "a:hover path,a:focus path{stroke:#f0efec}"]
    dark += [".b%d{fill:%s}" % (i, c) for i, c in enumerate(dk)]
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 9750 6100" role="img">',
           "<title>US county map of farm real estate value per acre</title>",
           "<style>%s@media (prefers-color-scheme:dark){%s}</style>" % ("".join(css), "".join(dark))]
    for fips in sorted(geo):
        g = geo[fips]
        d = path_d(g["p"])
        v = values.get(fips)
        cls = "b%d" % klass(v, cuts) if v is not None else "nd"
        shape = '<path class="%s" d="%s"><title>%s</title></path>' % (cls, d, esc(titles.get(fips) or g["n"]))
        if fips in links:
            out.append('<a href="%s" target="_top" tabindex="-1">%s</a>' % (esc(links[fips]), shape))
        else:
            out.append(shape)
    for s in sorted(geo_states.values(), key=lambda s: s["f"]):
        out.append('<path class="st" d="%s"/>' % path_d(s["p"]))
    out.append("</svg>")
    return "".join(out)


def state_map_svg(shapes, values, links, titles, cuts, label):
    """Inline SVG of one state's counties. shapes: [(fips, rings)]."""
    if not shapes:
        return ""
    x0, y0, x1, y1 = bbox([rings for _, rings in shapes])
    pad = max(x1 - x0, y1 - y0) * 0.03 + 4
    n = len(cuts) + 1
    out = ['<svg class="statemap" viewBox="%d %d %d %d" role="img" aria-label="%s">' % (
        x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad, esc(label))]
    for fips, rings in shapes:
        v = values.get(fips)
        cls = "q%d-%d" % (n, klass(v, cuts)) if v is not None else "nodata"
        shape = '<path class="%s" d="%s"><title>%s</title></path>' % (cls, path_d(rings), esc(titles.get(fips, "")))
        if fips in links:
            out.append('<a href="%s" tabindex="-1">%s</a>' % (esc(links[fips]), shape))
        else:
            out.append(shape)
    out.append("</svg>")
    return "".join(out)
