"""Build the static site into dist/ from data/.

    python3 -m landindex.build [dist]

Writes every page, the national map, CSV downloads, the JSON API, sitemap.xml, robots.txt, the IndexNow key file,
share-card sources (_og/*.html, rendered to PNG by scripts/og.py) and manifest.json (a hash per page, which the
deploy compares with the live site to tell IndexNow only about pages that changed).
"""
import csv
import hashlib
import io
import json
import os
import shutil
import sys

from . import config, maps
from .fmt import esc, money
from .model import Index, STATES
from .pages import Site

STATIC = ["style.css", "app.js", "embed.js", "favicon.svg"]


class Writer(object):
    def __init__(self, dist):
        self.dist = dist
        self.pages = {}     # site path -> sha1 of the page, for manifest.json
        self.files = 0

    def write(self, rel, text, page_path=None):
        full = os.path.join(self.dist, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        data = text.encode("utf-8") if isinstance(text, str) else text
        with open(full, "wb") as fh:
            fh.write(data)
        self.files += 1
        if page_path is not None:
            self.pages[page_path] = hashlib.sha1(data).hexdigest()[:16]

    def page(self, path, html_):
        rel = path.strip("/")
        self.write((rel + "/" if rel else "") + "index.html", html_, path)


def csv_text(header, rows):
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    return out.getvalue()


def num_out(v):
    if v is None:
        return None
    return int(v) if float(v) == int(v) else v


SERIES_HEADER = ["fips", "state", "county", "year", "value_per_acre", "kind"]


def series_rows(ix, fips_list):
    for f in fips_list:
        c = ix.counties[f]
        for y, v, k in c["series"]:
            yield [c["fips"], c["state"], c["name"], y, num_out(v), k]


def county_detail_rows(c):
    years = sorted(set([y for y, _, _ in c["series"]]) | set(c["census"]) | set(c["rent"]) | set(c["fhfa"]))
    by = {y: (v, k) for y, v, k in c["series"]}
    for y in years:
        cen = c["census"].get(y) or {}
        rent = c["rent"].get(y) or {}
        fh = c["fhfa"].get(y) or {}
        v, k = by.get(y, (None, None))
        yield [y, num_out(v), k, num_out(cen.get("value")), "1" if cen.get("suppressed") else "", cen.get("cv"),
               cen.get("acres"), cen.get("farms"), num_out(rent.get("nonirr")), num_out(rent.get("irr")),
               num_out(rent.get("pasture")), num_out(fh.get("per_acre")), num_out(fh.get("quarter")), fh.get("share")]


COUNTY_DETAIL_HEADER = ["year", "value_per_acre", "kind", "census_value_per_acre", "census_suppressed", "census_cv_pct",
                        "acres_in_farms", "farms", "cash_rent_cropland_nonirrigated", "cash_rent_cropland_irrigated",
                        "cash_rent_pasture", "fhfa_land_value_per_acre", "fhfa_quarter_acre_standardized",
                        "fhfa_land_share"]
LATEST_HEADER = ["fips", "state", "county", "census_year", "census_value_per_acre", "change_from_previous_census_pct",
                 "estimate_year", "estimate_value_per_acre", "acres_in_farms", "farms", "cash_rent_year",
                 "cash_rent_cropland_nonirrigated", "cash_rent_pasture", "fhfa_year", "fhfa_land_value_per_acre",
                 "fhfa_land_share", "rank_in_us", "page"]


def latest_rows(ix, site):
    cy = ix.census_year
    for f in sorted(ix.counties):
        c = ix.counties[f]
        cen = c["census"].get(cy) or {}
        est = c.get("estimate")
        rent = site.latest_rent(c)
        rent_row = c["rent"].get(rent[0]) if rent else {}
        fh = site.latest_fhfa(c)
        yield [f, c["state"], c["name"], cy if c["obs"].get(cy) else None, num_out(c["obs"].get(cy)),
               round(c["census_chg"], 1) if c.get("census_chg") is not None else None,
               est[0] if est else None, num_out(est[1]) if est else None, cen.get("acres"), cen.get("farms"),
               rent[0] if rent else None, num_out(rent[1]) if rent else None,
               num_out(rent_row.get("pasture")) if rent else None, fh[0] if fh else None,
               num_out(fh[1]["per_acre"]) if fh else None, fh[1]["share"] if fh else None, c.get("rank_us"),
               config.BASE_URL + ix.county_path(c)]


def og_card(title, value, sub, map_svg, foot):
    """1200x630 share card source. Rendered to PNG by scripts/og.py; the PNG falls back to site/og-default.png."""
    return (
        '<!doctype html><html><head><meta charset="utf-8"><style>'
        'html,body{margin:0;width:1200px;height:630px;overflow:hidden}'
        'body{background:#fcfcfb;color:#0b0b0b;font-family:system-ui,-apple-system,"Segoe UI",Roboto,"DejaVu Sans",sans-serif;'
        'display:grid;grid-template-columns:560px 1fr;gap:24px;padding:56px 56px 40px;box-sizing:border-box}'
        '.l{display:flex;flex-direction:column}.brand{font-size:24px;font-weight:650;color:#1c5cab}'
        'h1{font-size:50px;line-height:1.08;margin:26px 0 22px;letter-spacing:-.01em}'
        '.v{font-size:76px;font-weight:700;line-height:1}.v span{font-size:28px;font-weight:400;color:#52514e}'
        '.s{font-size:24px;color:#52514e;margin-top:12px}.f{margin-top:auto;font-size:19px;color:#6f6d68}'
        '.m{display:flex;align-items:center;justify-content:center}.m svg{width:100%%;height:100%%;max-height:520px}'
        '.m path{stroke:#fcfcfb;stroke-width:.6;vector-effect:non-scaling-stroke}%s'
        '</style></head><body><div class="l"><div class="brand">%s</div><h1>%s</h1><div class="v">%s</div>'
        '<div class="s">%s</div><div class="f">%s</div></div><div class="m">%s</div></body></html>'
    ) % (maps.legend_css().split("@media")[0], esc(config.SITE_NAME), esc(title), value, esc(sub), esc(foot), map_svg)


def build(dist, data_dir=None, log=print):
    ix = Index(data_dir)
    site = Site(ix)
    if os.path.isdir(dist):
        shutil.rmtree(dist)
    os.makedirs(dist)
    w = Writer(dist)
    cy = ix.census_year

    # --- static assets
    css = open(os.path.join(config.SITE_SRC, "style.css"), encoding="utf-8").read() + "\n/* map classes */\n" + maps.legend_css()
    w.write("assets/style.css", css)
    for name in STATIC[1:]:
        shutil.copy(os.path.join(config.SITE_SRC, name), os.path.join(dist, "assets", name))
    key = open(os.path.join(config.SITE_SRC, "indexnow-key.txt")).read().strip()
    w.write("%s.txt" % key, key)

    # --- national map
    values = {f: c["obs"][cy] for f, c in ix.counties.items() if c["obs"].get(cy) and c["has_shape"] and not c.get("usda_area")}
    cuts = maps.breaks(values.values(), 7)
    links = {f: site.u(ix.county_path(c)) for f, c in ix.counties.items() if c["has_shape"]}
    titles = {}
    for f, g in ix.geo.items():
        c = ix.counties.get(f)
        if c and f in values:
            titles[f] = "%s: %s per acre (%d census)" % (c["label"], money(values[f]), cy)
        elif c:
            titles[f] = "%s: no %d farm value; open for details" % (c["label"], cy)
        else:
            titles[f] = "%s, %s: no published value" % (g["n"], g["sn"])
    us_svg = maps.us_map_svg(ix.geo, ix.geo_states, values, links, titles, cuts)
    w.write("assets/us-counties.svg", us_svg)

    # --- pages
    w.page("/", site.home())
    w.page("/states/", site.states_index())
    w.page("/rankings/", site.rankings())
    w.page("/methodology/", site.methodology())
    w.page("/about/", site.about())
    w.write("embed/index.html", site.embed())
    w.write("404.html", site.not_found())
    for st in ix.states.values():
        if not st["counties"]:
            continue
        if st["code"] == "DC":
            continue  # the District is a single county-equivalent: its county page is the state page
        w.page(ix.state_path(st), site.state(st))
    for f in sorted(ix.counties):
        c = ix.counties[f]
        w.page(ix.county_path(c), site.county(c))
        w.write("api/county/%s.json" % f, json.dumps(ix.county_json(c), separators=(",", ":")))
        w.write("data/county/%s.csv" % f, csv_text(COUNTY_DETAIL_HEADER, county_detail_rows(c)))

    # --- downloads and API
    files = []
    text = csv_text(SERIES_HEADER, series_rows(ix, sorted(ix.counties)))
    w.write("data/county-land-index.csv", text)
    files.append(("/data/county-land-index.csv", "Every county and year: value per acre and whether it is a census observation or an estimate", text.count("\n") - 1))
    text = csv_text(LATEST_HEADER, latest_rows(ix, site))
    w.write("data/counties-latest.csv", text)
    files.append(("/data/counties-latest.csv", "One row per county: latest census value, estimate, cash rent, FHFA residential land value and rank", text.count("\n") - 1))
    for st in ix.states.values():
        if st["counties"]:
            w.write("data/state/%s.csv" % st["code"].lower(), csv_text(SERIES_HEADER, series_rows(ix, st["counties"])))
    from . import sources as src
    for name in sorted(src.FILES):
        path = os.path.join(ix.data_dir, name)
        if os.path.exists(path):
            shutil.copy(path, os.path.join(dist, "data", "source", name) if os.path.isdir(os.path.join(dist, "data", "source"))
                        else _mk(os.path.join(dist, "data", "source"), name))
            rows = sum(1 for _ in open(path, encoding="utf-8")) - 1
            files.append(("/data/source/%s" % name, "USDA or FHFA extract as published by the agency (" + name.split("_", 1)[0].upper() + ")", rows))
    status = dict(ix.status)
    status["site"] = {"base_url": config.BASE_URL, "census_year": cy, "survey_year": ix.survey_year,
                      "fhfa_year": ix.fhfa_year, "counties": len(ix.counties), "data_updated": site.updated(),
                      "commit": os.environ.get("GITHUB_SHA", "")}
    w.write("data/status.json", json.dumps(status, indent=1, sort_keys=True))
    w.page("/data/", site.data_page(files))

    search = []
    for f in sorted(ix.counties, key=lambda f: (ix.counties[f]["state_name"], ix.counties[f]["name"])):
        c = ix.counties[f]
        cur = c.get("current")
        if cur:
            row = [f, c["name"], c["state"], c["state_name"], ix.county_path(c), num_out(cur[1]), cur[0], cur[2][0]]
        else:
            fh = site.latest_fhfa(c)
            row = [f, c["name"], c["state"], c["state_name"], ix.county_path(c),
                   num_out(fh[1]["per_acre"]) if fh else None, fh[0] if fh else None, "r"]
        search.append(row)
    w.write("api/counties.json", json.dumps(search, separators=(",", ":")))
    states_api = []
    for st in sorted(ix.states.values(), key=lambda s: s["code"]):
        states_api.append({"state": st["code"], "name": st["name"], "url": config.BASE_URL + ix.state_path(st),
                           "survey_year": st["latest_year"], "farm_real_estate_per_acre": num_out(st["latest"]),
                           "census_year": cy, "census_value_per_acre": num_out(st.get("census_value")),
                           "counties": len(st["counties"])})
    w.write("api/states.json", json.dumps(states_api, separators=(",", ":")))
    w.write("api/us.json", json.dumps({
        "survey": [{"year": y, "farm_real_estate": num_out(v["all"]), "cropland": num_out(v["cropland"]),
                    "pasture": num_out(v["pasture"])} for y, v in sorted(ix.us["survey"].items())],
        "index_base_year": min(ix.us["index"]) if ix.us["index"] else None,
        "index": [{"year": y, "level": v} for y, v in sorted(ix.us["index"].items())]}, separators=(",", ":")))

    # --- share card sources
    us = ix.us
    w.write("_og/default.html", og_card(
        "Land prices per acre for every US county", money(us["latest"]) + " <span>per acre</span>",
        "US farm real estate, %d USDA survey" % ix.survey_year,
        maps.state_map_svg([(f, g["p"]) for f, g in sorted(ix.geo.items())], values, {}, {}, cuts, ""),
        "USDA and FHFA data. Not investment advice."))
    for st in ix.states.values():
        if not st["counties"]:
            continue
        shapes = [(f, g["p"]) for f, g in sorted(ix.geo.items()) if g["s"] == st["code"]]
        svals = {f: values[f] for f, _ in shapes if f in values}
        scuts = maps.breaks(svals.values(), 5)
        if st["latest"]:
            value, sub = money(st["latest"]) + " <span>per acre</span>", "Farm real estate, %d USDA survey" % st["latest_year"]
        elif st.get("census_value"):
            value, sub = money(st["census_value"]) + " <span>per acre</span>", "Farm real estate, %d census" % cy
        else:
            fy = max(st["fhfa"]) if st["fhfa"] else None
            value = money(st["fhfa"][fy]["per_acre"]) + " <span>per acre</span>" if fy else ""
            sub = "Residential land, %d (FHFA)" % fy if fy else ""
        w.write("_og/state-%s.html" % st["code"].lower(), og_card(
            "%s land prices by county" % st["name"], value, sub,
            maps.state_map_svg(shapes, svals, {}, {}, scuts, "") if len(svals) > 1 else "",
            "County values from USDA and FHFA. Not investment advice."))

    # --- crawl files
    urls = sorted(w.pages)
    lastmod = site.updated()
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in urls:
        sm.append("<url><loc>%s</loc>%s</url>" % (esc(config.BASE_URL + p), "<lastmod>%s</lastmod>" % lastmod if lastmod else ""))
    sm.append("</urlset>")
    w.write("sitemap.xml", "\n".join(sm) + "\n")
    w.write("robots.txt", "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % config.BASE_URL)
    w.write("manifest.json", json.dumps({"pages": w.pages, "data_updated": lastmod}, sort_keys=True, separators=(",", ":")))
    w.write(".nojekyll", "")
    log("built %d files, %d pages, %d counties into %s" % (w.files, len(w.pages), len(ix.counties), dist))
    return w


def _mk(folder, name):
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, name)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    dist = argv[0] if argv else os.path.join(config.ROOT, "dist")
    build(dist)
    return 0


if __name__ == "__main__":
    sys.exit(main())
