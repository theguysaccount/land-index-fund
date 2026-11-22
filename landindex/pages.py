"""Page bodies. Every sentence with a number in it is computed from the model, so pages stay true as data changes.

Public copy rules (also enforced by tests): this is a statistical index, never called a fund; no talk of returns;
every page carries the "not investment advice, not an appraisal" notice.
"""
import json

from . import config, maps
from .charts import line_chart, sparkline
from .fmt import direction, esc, money, num, ordinal, pct, plural, share
from .model import FIRST_INDEX_YEAR

NOTICE = ("A statistical summary of public USDA and FHFA data. Not investment advice, not an appraisal and not an "
          "offer to buy or sell anything. County figures are averages or estimates; a single parcel can be worth "
          "far more or far less.")
MIN_ACRES = 10000  # ranking tables skip counties with less farmland than this: a few city farms swing the average


class Site(object):
    def __init__(self, index):
        self.ix = index
        self.base = config.base_path()

    # ------------------------------------------------------------------ plumbing
    def u(self, path):
        return self.base + path

    def absu(self, path):
        return config.BASE_URL + path

    def checked(self):
        return self.ix.status.get("checked", "")

    def updated(self):
        """The last day any source's data changed. Stable between data changes, unlike the check date."""
        days = [s.get("changed", "") for s in self.ix.status.get("sources", {}).values()]
        return max([d for d in days if d] or [""])

    def layout(self, title, description, path, body, jsonld=None, og="default", noindex=False, wide=False):
        ix = self.ix
        head = [
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>%s</title>" % esc(title),
            '<meta name="description" content="%s">' % esc(description),
            '<link rel="canonical" href="%s">' % esc(self.absu(path)),
            '<meta name="robots" content="%s">' % ("noindex, follow" if noindex else "index, follow, max-image-preview:large"),
            '<meta property="og:type" content="website">',
            '<meta property="og:site_name" content="%s">' % esc(config.SITE_NAME),
            '<meta property="og:title" content="%s">' % esc(title),
            '<meta property="og:description" content="%s">' % esc(description),
            '<meta property="og:url" content="%s">' % esc(self.absu(path)),
            '<meta property="og:image" content="%s">' % esc(self.absu("/og/%s.png" % og)),
            '<meta property="og:image:width" content="1200">', '<meta property="og:image:height" content="630">',
            '<meta name="twitter:card" content="summary_large_image">',
            '<link rel="icon" href="%s" type="image/svg+xml">' % self.u("/assets/favicon.svg"),
            '<link rel="stylesheet" href="%s">' % self.u("/assets/style.css"),
            '<link rel="alternate" type="application/json" title="Data status" href="%s">' % self.u("/data/status.json"),
        ]
        if config.GOOGLE_VERIFY:
            head.append('<meta name="google-site-verification" content="%s">' % esc(config.GOOGLE_VERIFY))
        for block in jsonld or []:
            head.append('<script type="application/ld+json">%s</script>' % json.dumps(block, separators=(",", ":")).replace("</", "<\\/"))
        nav = "".join('<a href="%s">%s</a>' % (self.u(p), t) for p, t in (
            ("/states/", "States"), ("/rankings/", "Rankings"), ("/methodology/", "Method"), ("/data/", "Data")))
        support = ""
        if config.SUPPORT_URL:
            support = ' <a class="support" href="%s" rel="noopener sponsored">Support this index</a>' % esc(config.SUPPORT_URL)
        foot = (
            '<footer><div class="wrap"><p class="notice">%s</p>'
            '<p>Sources: <a href="https://www.nass.usda.gov/datasets" rel="noopener">USDA NASS Quick Stats</a> '
            '(Census of Agriculture, Land Values and Cash Rents surveys) and '
            '<a href="https://www.fhfa.gov/research/papers/wp1901" rel="noopener">FHFA Working Paper 19-01 land price data</a>. '
            'Data last updated %s.</p>'
            '<p><a href="%s">Method</a> · <a href="%s">Data and API</a> · <a href="%s">About</a> · '
            '<a href="%s" rel="noopener">Source code</a>%s</p></div></footer>'
        ) % (esc(NOTICE), esc(self.updated() or "n/a"), self.u("/methodology/"), self.u("/data/"), self.u("/about/"),
             esc(config.REPO_URL), support)
        scripts = '<script src="%s" defer></script>' % self.u("/assets/app.js")
        if config.GOATCOUNTER:
            scripts += '<script data-goatcounter="%s" async src="https://gc.zgo.at/count.js"></script>' % esc(config.GOATCOUNTER)
        return (
            '<!doctype html><html lang="en"><head>%s</head><body data-base="%s">'
            '<a class="skip" href="#main">Skip to content</a>'
            '<header><div class="wrap"><a class="brand" href="%s"><svg viewBox="0 0 24 24" aria-hidden="true">'
            '<path d="M2 20h20M4 20l5-9 4 5 3-4 4 8"/></svg>%s</a><nav aria-label="Main">%s</nav></div></header>'
            '<main id="main" class="wrap%s">%s</main>%s%s</body></html>'
        ) % ("".join(head), esc(self.base), self.u("/"), esc(config.SITE_SHORT), nav, " wide" if wide else "", body,
             foot, scripts)

    def crumbs(self, trail):
        """trail: [(name, path)] from the home page down. Returns (html, JSON-LD)."""
        items = [("Home", "/")] + trail
        html_ = '<nav class="crumbs" aria-label="Breadcrumb">%s</nav>' % " › ".join(
            ('<a href="%s">%s</a>' % (self.u(p), esc(n))) if i < len(items) - 1 else "<span>%s</span>" % esc(n)
            for i, (n, p) in enumerate(items))
        ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": self.absu(p)} for i, (n, p) in enumerate(items)]}
        return html_, ld

    def tiles(self, tiles):
        return '<div class="tiles">%s</div>' % "".join(
            '<div class="tile"><p class="tl">%s</p><p class="tv">%s</p><p class="ts">%s</p></div>' % (
                esc(label), value, sub) for label, value, sub in tiles if value)

    def dataset_ld(self, name, description, path, spatial, files):
        ix = self.ix
        years = "%d/%d" % (FIRST_INDEX_YEAR, ix.survey_year or ix.census_year)
        return {
            "@context": "https://schema.org", "@type": "Dataset", "name": name, "description": description,
            "url": self.absu(path), "isAccessibleForFree": True,
            "license": "https://creativecommons.org/publicdomain/zero/1.0/",
            "creator": {"@type": "Organization", "name": config.SITE_NAME, "url": self.absu("/")},
            "temporalCoverage": years, "spatialCoverage": {"@type": "Place", "name": spatial},
            "variableMeasured": ["Farm real estate value per acre (USD)", "Cash rent per acre (USD)",
                                 "Residential land value per acre (USD)"],
            "isBasedOn": ["https://www.nass.usda.gov/datasets", "https://www.fhfa.gov/research/papers/wp1901"],
            "dateModified": self.updated() or None,
            "distribution": [{"@type": "DataDownload", "encodingFormat": fmt, "contentUrl": self.absu(p)}
                             for fmt, p in files],
        }

    # ------------------------------------------------------------------ shared pieces
    def county_link(self, c, with_state=False):
        label = c["label"] if with_state else c["name"]
        return '<a href="%s">%s</a>' % (self.u(self.ix.county_path(c)), esc(label))

    def county_rows(self, fips_list, with_state=False, rank=False):
        """Table rows used by state pages, neighbour lists and rankings."""
        ix = self.ix
        cy, py, sy = ix.census_year, ix.prev_census_year, ix.survey_year
        rows = []
        for i, f in enumerate(fips_list):
            c = ix.counties[f]
            v = c["obs"].get(cy)
            est = c.get("estimate")
            rent = self.latest_rent(c)
            fh = self.latest_fhfa(c)
            acres = (c["census"].get(cy) or {}).get("acres")
            cells = []
            if rank:
                cells.append('<td class="n">%d</td>' % (i + 1))
            cells.append('<th scope="row">%s</th>' % self.county_link(c, with_state))
            cells.append('<td class="n" data-v="%s">%s</td>' % (v or "", money(v, "–")))
            cells.append('<td class="n" data-v="%s">%s</td>' % (c.get("census_chg", ""), pct(c.get("census_chg"), dash="–")))
            cells.append('<td class="n" data-v="%s">%s</td>' % (est[1] if est else "", money(est[1], "–") if est else "–"))
            cells.append('<td class="n" data-v="%s">%s</td>' % (rent[1] if rent else "", money(rent[1]) if rent else "–"))
            cells.append('<td class="n" data-v="%s">%s</td>' % (fh[1]["per_acre"] if fh else "", money(fh[1]["per_acre"]) if fh else "–"))
            cells.append('<td class="n" data-v="%s">%s</td>' % (acres or "", num(acres, "–")))
            rows.append("<tr>%s</tr>" % "".join(cells))
        return "".join(rows)

    def county_table(self, fips_list, with_state=False, rank=False, caption=""):
        ix = self.ix
        cy, py, sy = ix.census_year, ix.prev_census_year, ix.survey_year
        rent_year = max((max(c["rent"]) for c in ix.counties.values() if c["rent"]), default=None)
        head = ('<th scope="col" class="n">#</th>' if rank else "") + (
            '<th scope="col">County</th>'
            '<th scope="col" class="n" title="USDA Census of Agriculture, observed">%d census, $/acre</th>'
            '<th scope="col" class="n">Change from %d</th>'
            '<th scope="col" class="n" title="Census value moved by the state survey">%s estimate, $/acre</th>'
            '<th scope="col" class="n" title="USDA county cash rent, non-irrigated cropland, latest year">Cropland rent, $/acre</th>'
            '<th scope="col" class="n" title="FHFA, land under single-family homes, latest year">Residential land, $/acre</th>'
            '<th scope="col" class="n">Acres in farms, %d</th>') % (cy, py or 0, sy or cy, cy)
        return ('<div class="scroll"><table class="data sortable">%s<thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>'
                % ("<caption>%s</caption>" % esc(caption) if caption else "", head,
                   self.county_rows(fips_list, with_state, rank)))

    def latest_rent(self, c):
        """(year, non-irrigated cropland rent) for the newest year that has one."""
        for y in sorted(c["rent"], reverse=True):
            if c["rent"][y]["nonirr"] is not None:
                return y, c["rent"][y]["nonirr"]
        return None

    def latest_fhfa(self, c):
        for y in sorted(c["fhfa"], reverse=True):
            if c["fhfa"][y]["per_acre"] is not None:
                return y, c["fhfa"][y]
        return None

    def search_box(self, label="Find a county"):
        return ('<form class="finder" role="search" onsubmit="return false"><label for="q">%s</label>'
                '<input id="q" type="search" autocomplete="off" spellcheck="false" placeholder="Type a county or state, for example Story County" '
                'aria-controls="q-results"><ul id="q-results" class="results" hidden></ul>'
                '<noscript><p>Search needs JavaScript. <a href="%s">Browse counties by state</a> instead.</p></noscript></form>'
                ) % (esc(label), self.u("/states/"))

    def reading_notes(self, state_name=None):
        ix = self.ix
        return (
            '<section><h2>How to read these numbers</h2><ul class="notes">'
            '<li><strong>They are averages, not prices.</strong> USDA\'s figure is the estimated market value of all '
            'farm land and buildings in the county divided by the acres in farms. Cropland, pasture, woodland, '
            'irrigated land and land near a town sell for very different amounts.</li>'
            '<li><strong>Census years are observations; other years are estimates.</strong> USDA values every county '
            'only in its five-yearly Census of Agriculture. Between and after censuses this index moves the county '
            'with its state\'s annual USDA survey. That assumes the county tracked its state, which is not always true.</li>'
            '<li><strong>Farm operators report the values.</strong> The census asks operators what their land and buildings '
            'would sell for. Counties with few farms have noisier figures; USDA\'s coefficient of variation (CV) is shown where published.</li>'
            '<li><strong>Not advice.</strong> Nothing here is investment advice or an appraisal. '
            'Before any land decision, look at recorded sales, a current appraisal and the parcel itself.</li>'
            '</ul><p><a href="%s">Full method and limits</a></p></section>') % self.u("/methodology/")

    # ------------------------------------------------------------------ county page
    def county(self, c):
        ix = self.ix
        st = ix.states[c["state"]]
        cy, py, sy = ix.census_year, ix.prev_census_year, ix.survey_year
        name, sname = c["name"], c["state_name"]
        path = ix.county_path(c)
        obs = c["obs"]
        est = c.get("estimate")
        latest = c.get("latest_obs")
        rent = self.latest_rent(c)
        fh = self.latest_fhfa(c)
        is_dc = c["state"] == "DC"
        trail = [(name, path)] if is_dc else [(sname, ix.state_path(st)), (name, path)]
        crumbs, crumb_ld = self.crumbs(trail)

        # --- lede
        p = []
        if latest and latest[0] == cy:
            s = "Farm real estate in %s averaged <strong>%s per acre</strong> in USDA's %d Census of Agriculture" % (
                esc(name), money(latest[1]), cy)
            vs = c.get("vs_state")
            if vs is not None and c.get("n_state", 0) > 1:
                if abs(vs) < 0.5:
                    s += ", about the same as the %s average" % esc(sname)
                else:
                    s += ", %s %s the %s average" % (pct(abs(vs), 0, signed=False), "above" if vs > 0 else "below", esc(sname))
                s += " and the %s highest of %s %s %s with a published value" % (
                    ordinal(c["rank_state"]), num(c["n_state"]), esc(sname), "areas" if c["state"] == "AK" else "counties")
            p.append(s + ".")
            if est:
                p.append("Carried forward with %s's annual USDA survey, the %d estimate is about <strong>%s per acre</strong>." % (
                    esc(sname), est[0], money(est[1])))
            elif not st["series"]:
                p.append("USDA runs no annual land value survey for %s, so this index makes no estimate after %d." % (esc(sname), cy))
        elif latest:
            p.append("USDA withheld %s's %d figure to avoid disclosing individual farms. The latest published value is "
                     "<strong>%s per acre</strong>, from the %d Census of Agriculture. This index makes no estimate from a figure that old."
                     % (esc(name), cy, money(latest[1]), latest[0]))
        else:
            p.append("USDA publishes no farm real estate value for %s: it has too few farms, or none. "
                     "The residential land figures below come from FHFA." % esc(name))
        if c.get("usda_area") and obs:
            p.append("USDA reports Alaska's farmland for five multi-borough areas, not for single boroughs. "
                     "The farm figures on this page are for the <strong>%s</strong>, which includes %s." % (
                         esc(c["usda_area"]), esc(name) if c["has_shape"] else "this part of the state"))
        lede = '<p class="lede">%s</p>' % " ".join(p)

        # --- tiles
        tiles = []
        if est:
            moved = pct(pct_change(st["series"].get(est[0]), st["series"].get(est[2])))
            tiles.append(("%d estimate" % est[0], money(est[1]) + ' <span class="per">per acre</span>',
                          "%d census value, moved with %s (%s since)" % (est[2], esc(sname), moved)))
        if latest:
            sub = "%s from %d" % (pct(c["census_chg"]), py) if c.get("census_chg") is not None else "USDA Census of Agriculture"
            tiles.append(("%d census, observed" % latest[0], money(latest[1]) + ' <span class="per">per acre</span>', sub))
        if c.get("rank_state") and c.get("n_state", 0) > 1:
            tiles.append(("Rank in %s, %d" % (sname, cy), "%s <span class=\"per\">of %s</span>" % (num(c["rank_state"]), num(c["n_state"])),
                          "%s of %s US counties" % (ordinal(c["rank_us"]), num(c["n_us"]))))
        elif c.get("rank_us"):
            tiles.append(("US rank, %d" % cy, "%s <span class=\"per\">of %s</span>" % (num(c["rank_us"]), num(c["n_us"])), "counties with a published value"))
        if rent:
            pasture = c["rent"][rent[0]]["pasture"]
            tiles.append(("Cropland rent, %d" % rent[0], money(rent[1]) + ' <span class="per">per acre</span>',
                          "non-irrigated" + ("; pasture %s" % money(pasture) if pasture is not None else "")))
        elif fh:
            tiles.append(("Residential land, %d" % fh[0], money(fh[1]["per_acre"]) + ' <span class="per">per acre</span>',
                          "FHFA, land under single-family homes"))
        if len(tiles) < 4 and fh and rent:
            tiles.append(("Residential land, %d" % fh[0], money(fh[1]["per_acre"]) + ' <span class="per">per acre</span>',
                          "FHFA, land under single-family homes"))
        body = [crumbs, "<h1>Land prices in %s</h1>" % esc(c["label"]), lede, self.tiles(tiles[:4])]

        # --- chart
        if len(c["series"]) > 1:
            first, last = c["series"][0][0], c["series"][-1][0]
            series = [{"name": name, "slot": 1, "points": c["series"]}]
            state_pts = [(y, st["series"][y], "") for y in range(first, last + 1) if st["series"].get(y)]
            if state_pts and c.get("n_state", 0) > 1:
                series.append({"name": "%s average (USDA survey)" % sname, "slot": 2, "points": state_pts})
            svg, legend = line_chart(series, "Farm real estate value per acre in %s, %d to %d" % (c["label"], first, last),
                                     marks=ix.census_years)
            rows = []
            st_by = dict((a, b) for a, b, _ in state_pts)
            for y, v, kind in c["series"]:
                rows.append('<tr><th scope="row">%d</th><td class="n">%s</td><td>%s</td><td class="n">%s</td></tr>' % (
                    y, money(v), {"census": "Census (observed)", "interpolated": "Estimate between censuses",
                                  "estimate": "Estimate after the census"}[kind], money(st_by.get(y), "–")))
            if any(k == "interpolated" for _, _, k in c["series"]):
                cap = ("Farm real estate (land and buildings) per acre. Dots are Census of Agriculture observations. "
                       "Between them the line follows %s's annual USDA survey" % esc(sname))
                cap += "; the dashed part is the estimate since %d." % est[2] if est else "."
            else:
                cap = ("Farm real estate (land and buildings) per acre. Dots are Census of Agriculture observations, joined by "
                       "straight lines: USDA's annual land value survey does not cover %s, so there are no yearly estimates." % esc(sname))
            body.append(
                '<section><h2>Value per acre, %d to %d</h2><figure>%s%s<figcaption>%s</figcaption></figure>'
                '<details><summary>Show every year as a table</summary><div class="scroll"><table class="data">'
                '<thead><tr><th scope="col">Year</th><th scope="col" class="n">%s, $/acre</th><th scope="col">Basis</th>'
                '<th scope="col" class="n">%s, $/acre</th></tr></thead><tbody>%s</tbody></table></div></details></section>'
                % (first, last, legend, svg, cap, esc(name), esc(sname), "".join(rows)))

        # --- census record
        if c["census"]:
            rows, prev = [], None
            for y in ix.census_years:
                r = c["census"].get(y)
                if not r:
                    rows.append('<tr><th scope="row">%d</th><td class="n">not published</td><td class="n">–</td><td class="n">–</td><td class="n">–</td><td class="n">–</td></tr>' % y)
                    continue
                if r["value"] is None:
                    val = "withheld" if r["suppressed"] else "not published"
                    chg = "–"
                else:
                    val = money(r["value"])
                    chg = pct(pct_change(r["value"], prev[1])) + (" from %d" % prev[0] if prev and prev[0] != y - 5 else "") if prev else "–"
                    prev = (y, r["value"])
                rows.append('<tr><th scope="row">%d</th><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td></tr>' % (
                    y, val, chg, num(r["acres"], "–"), num(r["farms"], "–"), ("%s%%" % ("%g" % r["cv"])) if r["cv"] is not None else "–"))
            area_note = " for the %s" % esc(c["usda_area"]) if c.get("usda_area") else ""
            body.append(
                '<section><h2>Census of Agriculture record</h2><p>What USDA published%s in each census. '
                '"Withheld" means USDA suppressed the figure so that no single farm could be identified.</p>'
                '<div class="scroll"><table class="data"><thead><tr><th scope="col">Census</th>'
                '<th scope="col" class="n">Land and buildings, $/acre</th><th scope="col" class="n">Change</th>'
                '<th scope="col" class="n">Acres in farms</th><th scope="col" class="n">Farms</th>'
                '<th scope="col" class="n" title="Coefficient of variation of the value per acre: lower is more reliable">CV</th>'
                '</tr></thead><tbody>%s</tbody></table></div></section>' % (area_note, "".join(rows)))

        # --- cash rents
        rent_years = [y for y in sorted(c["rent"]) if any(v is not None for v in c["rent"][y].values())]
        if rent_years:
            rows = []
            for y in rent_years[-8:]:
                r = c["rent"][y]
                rows.append('<tr><th scope="row">%d</th><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td></tr>' % (
                    y, money(r["nonirr"], "–"), money(r["irr"], "–"), money(r["pasture"], "–")))
            body.append(
                '<section><h2>Cash rents</h2><p>What tenants paid to rent farmland in %s, per acre per year, from USDA\'s '
                'county cash rents survey. A dash means USDA published no figure that year.</p>'
                '<div class="scroll"><table class="data"><thead><tr><th scope="col">Year</th>'
                '<th scope="col" class="n">Cropland, non-irrigated</th><th scope="col" class="n">Cropland, irrigated</th>'
                '<th scope="col" class="n">Pasture</th></tr></thead><tbody>%s</tbody></table></div></section>'
                % (esc(name), "".join(rows)))

        # --- FHFA
        body.append(self.fhfa_section(c, fh))

        # --- neighbours
        if c["neighbors"]:
            nb = sorted(c["neighbors"], key=lambda f: ix.counties[f]["label"])
            body.append('<section><h2>Neighboring counties</h2>%s</section>' % self.county_table(nb, with_state=True))

        body.append(self.reading_notes())

        # --- reuse
        embed = '<iframe src="%s" title="Land prices in %s" width="100%%" height="250" loading="lazy" style="border:0;max-width:520px"></iframe>' % (
            self.absu("/embed/?fips=%s" % c["fips"]), esc(c["label"]))
        cite = "%s, “Land prices in %s”, from USDA NASS and FHFA data, %s (data updated %s)." % (
            config.SITE_NAME, c["label"], self.absu(path), self.updated() or "n/a")
        body.append(
            '<section><h2>Use this data</h2><p>Free to reuse, with or without credit. '
            '<a href="%s">CSV for this county</a> · <a href="%s">JSON</a> · <a href="%s">All downloads</a></p>'
            '<p class="lbl">Cite this page</p><p class="copy" data-copy>%s</p>'
            '<p class="lbl">Embed a live card</p><p class="copy" data-copy>%s</p></section>'
            % (self.u("/data/county/%s.csv" % c["fips"]), self.u("/api/county/%s.json" % c["fips"]), self.u("/data/"),
               esc(cite), esc(embed)))

        # --- meta
        if latest and latest[0] == cy:
            desc = "Farm real estate in %s averaged %s per acre in USDA's %d Census of Agriculture" % (c["label"], money(latest[1]), cy)
            if c.get("census_chg") is not None:
                desc += ", %s from %d" % (pct(c["census_chg"]), py)
            desc += "."
            if est:
                desc += " %d estimate: about %s. Trend, cash rents and residential land values." % (est[0], money(est[1]))
            else:
                desc += " Trend, census record and nearby counties."
        elif latest:
            desc = "The latest USDA farm real estate value for %s is %s per acre (%d census). Census record and residential land values." % (
                c["label"], money(latest[1]), latest[0])
        else:
            desc = "FHFA residential land values per acre for %s. USDA publishes no farm real estate value for this county." % c["label"]
        title = "%s land prices per acre | %s" % (c["label"], config.SITE_SHORT)
        ld = self.dataset_ld("Land prices per acre in %s" % c["label"], desc, path, c["label"],
                             [("text/csv", "/data/county/%s.csv" % c["fips"]), ("application/json", "/api/county/%s.json" % c["fips"])])
        return self.layout(title, desc, path, "".join(body), [crumb_ld, ld], og="state-%s" % c["state"].lower())

    def fhfa_section(self, c, fh):
        ix = self.ix
        if not fh and not c.get("fhfa_cs"):
            return ""
        name = c["name"]
        intro = ("<p>FHFA estimates the value of the land under single-family homes from millions of appraisals. "
                 "These are developed, residential lots, so they are not comparable acre for acre with farmland. "
                 "FHFA calls the series experimental.</p>")
        out = ['<section><h2>Residential land (FHFA)</h2>', intro]
        if fh:
            y, r = fh
            s = "In %d, land under single-family homes in %s was valued at <strong>%s per acre</strong>" % (y, esc(name), money(r["per_acre"]))
            if r["quarter"] is not None:
                s += ", or %s for a standardized quarter-acre lot" % money(r["quarter"])
            if r["share"] is not None:
                s += ". Land made up %s of the typical home's value" % share(r["share"])
            s += "."
            usda = c["obs"].get(y) or (c["obs"].get(ix.census_year) if abs(y - (ix.census_year or y)) <= 2 else None)
            if usda and r["per_acre"]:
                ratio = r["per_acre"] / usda
                if ratio >= 1.5:
                    s += (" That is about %s times the county's average farm real estate value per acre. The gap reflects "
                          "location, zoning, roads and utilities, not a like-for-like price difference.") % (
                              num(ratio) if ratio >= 10 else ("%.1f" % ratio).rstrip("0").rstrip("."))
            out.append("<p>%s</p>" % s)
            rows = []
            for yr in sorted(c["fhfa"]):
                v = c["fhfa"][yr]
                rows.append('<tr><th scope="row">%d</th><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td></tr>' % (
                    yr, money(v["per_acre"], "–"), money(v["quarter"], "–"), share(v["share"], "–")))
            out.append('<div class="scroll"><table class="data"><thead><tr><th scope="col">Year</th>'
                       '<th scope="col" class="n">Land value, $/acre (as is)</th>'
                       '<th scope="col" class="n">Quarter-acre lot (standardized)</th>'
                       '<th scope="col" class="n">Land share of home value</th></tr></thead><tbody>%s</tbody></table></div>' % "".join(rows))
        else:
            cs = c["fhfa_cs"]
            years = "%d to %d" % (ix.fhfa_years[0], ix.fhfa_year) if ix.fhfa_years else "all years"
            s = ("FHFA has no year-by-year series for %s, only an estimate pooled over %s: <strong>%s per acre</strong>"
                 % (esc(name), years, money(cs["per_acre"])))
            if cs["quarter"] is not None:
                s += ", or %s for a standardized quarter-acre lot" % money(cs["quarter"])
            if cs["share"] is not None:
                s += ", with land at %s of the typical home's value" % share(cs["share"])
            out.append("<p>%s.</p>" % s)
        out.append("</section>")
        return "".join(out)

    # ------------------------------------------------------------------ state page
    def state(self, st):
        ix = self.ix
        cy, py, sy = ix.census_year, ix.prev_census_year, ix.survey_year
        name, code = st["name"], st["code"]
        path = ix.state_path(st)
        crumbs, crumb_ld = self.crumbs([(name, path)])
        counties = [ix.counties[f] for f in st["counties"]]
        ly = st["latest_year"]
        sv = st["survey"].get(ly, {}) if ly else {}
        p, tiles = [], []
        if ly:
            s = "Farm real estate in %s averaged <strong>%s per acre</strong> in USDA's %d land values survey" % (esc(name), money(st["latest"]), ly)
            if st.get("chg1") is not None:
                d = direction(st["chg1"])
                s += ", %s" % ("unchanged from %d" % (ly - 1) if d == "unchanged" else "%s %s from %d" % (d, pct(abs(st["chg1"]), signed=False), ly - 1))
            p.append(s + ".")
            extra = []
            if sv.get("cropland"):
                extra.append("cropland averaged %s" % money(sv["cropland"]))
            if sv.get("pasture"):
                extra.append("pasture %s" % money(sv["pasture"]))
            if extra:
                p.append((" and ".join(extra) + " per acre.").capitalize())
            tiles.append(("Farm real estate, %d" % ly, money(st["latest"]) + ' <span class="per">per acre</span>',
                          "%s from %d" % (pct(st["chg1"]), ly - 1) if st.get("chg1") is not None else "USDA survey"))
            if sv.get("cropland"):
                tiles.append(("Cropland, %d" % ly, money(sv["cropland"]) + ' <span class="per">per acre</span>', "USDA survey"))
            if sv.get("pasture"):
                tiles.append(("Pasture, %d" % ly, money(sv["pasture"]) + ' <span class="per">per acre</span>', "USDA survey"))
        elif st.get("census_value"):
            p.append("USDA's annual land values survey does not cover %s. In the %d Census of Agriculture, farm real estate "
                     "in the state averaged <strong>%s per acre</strong>." % (esc(name), cy, money(st["census_value"])))
            tiles.append(("Farm real estate, %d census" % cy, money(st["census_value"]) + ' <span class="per">per acre</span>',
                          "%s from %d" % (pct(st["census_chg"]), py) if st.get("census_chg") is not None else ""))
        if st.get("rank_us"):
            tiles.append(("Rank among states, %d census" % cy, "%s <span class=\"per\">of %s</span>" % (num(st["rank_us"]), num(st["n_us"])),
                          "%s per acre in the census" % money(st["census_value"])))
        ranked = [c for c in counties if c["obs"].get(cy)]
        if len(ranked) > 1:
            hi = max(ranked, key=lambda c: c["obs"][cy])
            lo = min(ranked, key=lambda c: c["obs"][cy])
            p.append("County averages in the %d Census of Agriculture ran from %s in %s to %s in %s." % (
                cy, money(lo["obs"][cy]), self.county_link(lo), money(hi["obs"][cy]), self.county_link(hi)))
        body = [crumbs, "<h1>%s land prices per acre, by county</h1>" % esc(name), '<p class="lede">%s</p>' % " ".join(p),
                self.tiles(tiles[:4])]

        # chart
        if st["series"]:
            first = max(FIRST_INDEX_YEAR, min(st["series"]))
            series = [{"name": "Farm real estate", "slot": 1,
                       "points": [(y, v, "") for y, v in sorted(st["series"].items()) if y >= first]}]
            crop = [(y, v["cropland"], "") for y, v in sorted(st["survey"].items()) if y >= first and v["cropland"]]
            past = [(y, v["pasture"], "") for y, v in sorted(st["survey"].items()) if y >= first and v["pasture"]]
            if crop:
                series.append({"name": "Cropland", "slot": 2, "points": crop})
            if past:
                series.append({"name": "Pasture", "slot": 3, "points": past})
            svg, legend = line_chart(series, "%s farm real estate, cropland and pasture value per acre" % name)
            rows = []
            for y in sorted(st["survey"]):
                v = st["survey"][y]
                if v["all"] or v["cropland"] or v["pasture"]:
                    rows.append('<tr><th scope="row">%d</th><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td></tr>' % (
                        y, money(v["all"], "–"), money(v["cropland"], "–"), money(v["pasture"], "–")))
            body.append(
                '<section><h2>Value per acre since %d</h2><figure>%s%s<figcaption>USDA\'s annual survey values for %s. '
                'Farm real estate is all land and buildings on farms.</figcaption></figure>'
                '<details><summary>Show every year USDA has published, back to %d</summary><div class="scroll"><table class="data">'
                '<thead><tr><th scope="col">Year</th><th scope="col" class="n">Farm real estate</th>'
                '<th scope="col" class="n">Cropland</th><th scope="col" class="n">Pasture</th></tr></thead>'
                '<tbody>%s</tbody></table></div></details></section>'
                % (first, legend, svg, esc(name), min(st["survey"]), "".join(rows)))

        # map
        shapes = [(c["fips"], ix.geo[c["fips"]]["p"]) for c in counties if c["has_shape"]]
        extra_shapes = [(f, g["p"]) for f, g in ix.geo.items() if g["s"] == code and f not in ix.counties]
        values = {c["fips"]: c["obs"].get(cy) for c in counties if c["obs"].get(cy) and not c.get("usda_area")}
        if shapes and len(values) > 1:
            cuts = maps.breaks(values.values(), 5)
            links = {c["fips"]: self.u(ix.county_path(c)) for c in counties}
            titles = {c["fips"]: "%s: %s" % (c["name"], money(values[c["fips"]]) + " per acre" if c["fips"] in values else "no published value")
                      for c in counties}
            svg = maps.state_map_svg(sorted(shapes + extra_shapes), values, links, titles, cuts,
                                     "Map of %s counties by farm real estate value per acre, %d census" % (name, cy))
            body.append('<section><h2>County map</h2><div class="mapbox">%s</div>%s'
                        '<p class="small">Colours split %s\'s counties into equal-sized groups by their %d census value. '
                        'Select a county to open its page.</p></section>'
                        % (svg, maps.legend_html(cuts, "Farm real estate, $ per acre, %d census" % cy), esc(name), cy))

        # county table
        if counties:
            body.append('<section><h2>Every county in %s</h2><p>Select a column heading to sort.</p>%s</section>'
                        % (esc(name), self.county_table(st["counties"])))

        # state rents and FHFA
        rent_years = [y for y in sorted(st["rent"]) if any(v is not None for v in st["rent"][y].values())]
        if rent_years:
            ry = rent_years[-1]
            r = st["rent"][ry]
            bits = []
            if r["cropland"] is not None:
                bits.append("%s per acre for cropland" % money(r["cropland"]))
            if r["nonirr"] is not None and r["irr"] is not None:
                bits.append("%s non-irrigated and %s irrigated" % (money(r["nonirr"]), money(r["irr"])))
            if r["pasture"] is not None:
                bits.append("%s for pasture" % money(r["pasture"]))
            if bits:
                body.append('<section><h2>Cash rents</h2><p>In %d, %s tenants paid an average of %s, according to USDA\'s cash rents survey. '
                            'County figures are in the table above and on each county page.</p></section>' % (ry, esc(name), ", ".join(bits)))
        if st["fhfa"]:
            fy = max(st["fhfa"])
            r = st["fhfa"][fy]
            body.append('<section><h2>Residential land (FHFA)</h2><p>FHFA put the land under single-family homes in %s at '
                        '<strong>%s per acre</strong> in %d, with land making up %s of the typical home\'s value. '
                        'These are developed residential lots, so they are not comparable acre for acre with farmland. '
                        'FHFA calls the series experimental.</p></section>' % (esc(name), money(r["per_acre"]), fy, share(r["share"])))
        body.append(self.reading_notes())
        body.append('<section><h2>Use this data</h2><p>Free to reuse, with or without credit. <a href="%s">CSV of every %s county and year</a> · '
                    '<a href="%s">All downloads</a></p></section>' % (self.u("/data/state/%s.csv" % code.lower()), esc(name), self.u("/data/")))

        if ly:
            desc = "Farm real estate in %s averaged %s per acre in %d. Land values, cash rents and trends for %s %s %s, from USDA and FHFA data." % (
                name, money(st["latest"]), ly, "all" if len(counties) > 1 else "its", num(len(counties)) if len(counties) > 1 else "",
                plural(len(counties), "county", "counties"))
        else:
            desc = "Farm real estate in %s averaged %s per acre in the %d Census of Agriculture. Land values by county from USDA and FHFA data." % (
                name, money(st.get("census_value")), cy)
        desc = " ".join(desc.split())
        title = "%s land prices per acre by county | %s" % (name, config.SITE_SHORT)
        ld = self.dataset_ld("Land prices per acre in %s by county" % name, desc, path, name,
                             [("text/csv", "/data/state/%s.csv" % code.lower())])
        return self.layout(title, desc, path, "".join(body), [crumb_ld, ld], og="state-%s" % code.lower(), wide=True)

    # ------------------------------------------------------------------ home
    def home(self):
        ix = self.ix
        cy, py, sy = ix.census_year, ix.prev_census_year, ix.survey_year
        us = ix.us
        sv = us["survey"].get(sy, {})
        n_counties = len(ix.counties)
        d = direction(us["chg1"])
        p = ("A free index of land values for %s US counties, built from USDA's Census of Agriculture, USDA's annual land "
             "values survey and FHFA's residential land data. US farm real estate averaged <strong>%s per acre</strong> in %d, %s."
             ) % (num(n_counties), money(us["latest"]), sy,
                  "unchanged from %d" % (sy - 1) if d == "unchanged" else "%s %s from %d" % (d, pct(abs(us["chg1"]), signed=False), sy - 1))
        tiles = [("US farm real estate, %d" % sy, money(us["latest"]) + ' <span class="per">per acre</span>', "%s from %d" % (pct(us["chg1"]), sy - 1))]
        if sv.get("cropland"):
            tiles.append(("US cropland, %d" % sy, money(sv["cropland"]) + ' <span class="per">per acre</span>', "USDA survey"))
        if sv.get("pasture"):
            tiles.append(("US pasture, %d" % sy, money(sv["pasture"]) + ' <span class="per">per acre</span>', "USDA survey"))
        if us["index"].get(sy):
            tiles.append(("Index level, %d" % sy, "%s" % ("%.0f" % us["index"][sy]), "US farm real estate, %d = 100" % FIRST_INDEX_YEAR))
        body = ["<h1>US land prices per acre, by county</h1>", '<p class="lede">%s</p>' % p, self.search_box(), self.tiles(tiles)]

        # map
        values = {f: c["obs"][cy] for f, c in ix.counties.items() if c["obs"].get(cy) and c["has_shape"] and not c.get("usda_area")}
        cuts = maps.breaks(values.values(), 7)
        body.append(
            '<section><h2>Farm real estate value per acre, %d census</h2>'
            '<div class="mapbox us"><object type="image/svg+xml" data="%s" aria-label="US county map of farm real estate value per acre">'
            '<p>The map needs SVG support. <a href="%s">Browse counties by state</a>.</p></object></div>%s'
            '<p class="small">Each county is coloured by USDA\'s average value of farm land and buildings per acre. '
            'Select a county to open its page, or <a href="%s">browse by state</a>.</p></section>'
            % (cy, self.u("/assets/us-counties.svg"), self.u("/states/"),
               maps.legend_html(cuts, "$ per acre, %d Census of Agriculture" % cy), self.u("/states/")))

        # national chart
        first = FIRST_INDEX_YEAR
        series = [{"name": "Farm real estate", "slot": 1, "points": [(y, v, "") for y, v in sorted(us["series"].items()) if y >= first]}]
        crop = [(y, v["cropland"], "") for y, v in sorted(us["survey"].items()) if y >= first and v["cropland"]]
        past = [(y, v["pasture"], "") for y, v in sorted(us["survey"].items()) if y >= first and v["pasture"]]
        if crop:
            series.append({"name": "Cropland", "slot": 2, "points": crop})
        if past:
            series.append({"name": "Pasture", "slot": 3, "points": past})
        svg, legend = line_chart(series, "US farm real estate, cropland and pasture value per acre")
        rows = []
        for y in sorted(us["survey"]):
            v = us["survey"][y]
            if v["all"]:
                rows.append('<tr><th scope="row">%d</th><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td></tr>' % (
                    y, money(v["all"]), money(v["cropland"], "–"), money(v["pasture"], "–"),
                    ("%.0f" % us["index"][y]) if y in us["index"] else "–"))
        body.append(
            '<section><h2>The national series since %d</h2><figure>%s%s<figcaption>USDA\'s annual survey values for the 48 contiguous states, '
            'in dollars of each year (not adjusted for inflation).</figcaption></figure>'
            '<details><summary>Show every year USDA has published, back to %d</summary><div class="scroll"><table class="data"><thead><tr>'
            '<th scope="col">Year</th><th scope="col" class="n">Farm real estate</th><th scope="col" class="n">Cropland</th>'
            '<th scope="col" class="n">Pasture</th><th scope="col" class="n">Index, %d = 100</th></tr></thead><tbody>%s</tbody></table></div></details></section>'
            % (first, legend, svg, min(us["survey"]), FIRST_INDEX_YEAR, "".join(rows)))

        # states table
        body.append('<section><h2>States</h2>%s<p><a href="%s">All states and counties</a></p></section>' % (self.states_table(), self.u("/states/")))

        # movers
        big = self.big_counties()
        top = sorted(big, key=lambda c: -c["obs"][cy])[:10]
        body.append('<section><h2>Highest county averages</h2><p>Counties with at least %s acres in farms, ranked by their %d census value. '
                    '<a href="%s">Full rankings</a></p>%s</section>' % (num(MIN_ACRES), cy, self.u("/rankings/"),
                                                                  self.county_table([c["fips"] for c in top], with_state=True, rank=True)))
        body.append(
            '<section><h2>How the index works</h2><p>USDA values every county\'s farm real estate once every five years, in the Census of Agriculture. '
            'USDA also surveys every state every year. The index joins the two: each county\'s census values are observations, '
            'and the years between and after them are estimates that move with the county\'s state. '
            'Where FHFA publishes residential land values for a county, they are shown alongside. '
            '<a href="%s">Read the method</a> or <a href="%s">download the data</a>.</p></section>' % (self.u("/methodology/"), self.u("/data/")))
        desc = ("Free land price index for %s US counties: farm real estate value per acre from USDA's Census of Agriculture and annual survey, "
                "cash rents, and FHFA residential land values. US average %s per acre in %d.") % (num(n_counties), money(us["latest"]), sy)
        title = "US land prices per acre by county | %s" % config.SITE_NAME
        ld = [self.dataset_ld("US County Land Index", desc, "/", "United States",
                              [("text/csv", "/data/county-land-index.csv"), ("text/csv", "/data/counties-latest.csv")]),
              {"@context": "https://schema.org", "@type": "WebSite", "name": config.SITE_NAME, "url": self.absu("/"),
               "description": config.TAGLINE}]
        return self.layout(title, desc, "/", "".join(body), ld, wide=True)

    def big_counties(self):
        cy = self.ix.census_year
        return [c for c in self.ix.counties.values()
                if c["obs"].get(cy) and ((c["census"].get(cy) or {}).get("acres") or 0) >= MIN_ACRES and not c.get("usda_area")]

    def states_table(self):
        ix = self.ix
        cy, py, sy = ix.census_year, ix.prev_census_year, ix.survey_year
        rows = []
        for st in sorted(ix.states.values(), key=lambda s: s["name"]):
            if not st["counties"]:
                continue
            path = ix.state_path(st)
            vals = [st["series"].get(y) for y in range((sy or cy) - 19, (sy or cy) + 1)]
            rows.append(
                '<tr><th scope="row"><a href="%s">%s</a></th><td class="n" data-v="%s">%s</td><td class="n" data-v="%s">%s</td>'
                '<td class="n" data-v="%s">%s</td><td class="n" data-v="%s">%s</td><td class="n" data-v="%s">%s</td><td class="sp">%s</td></tr>' % (
                    self.u(path), esc(st["name"]), st.get("latest") or "", money(st.get("latest"), "–"),
                    st.get("chg1") if st.get("chg1") is not None else "", pct(st.get("chg1"), dash="–"),
                    st.get("census_value") or "", money(st.get("census_value"), "–"),
                    st.get("census_chg") if st.get("census_chg") is not None else "", pct(st.get("census_chg"), dash="–"),
                    len(st["counties"]), num(len(st["counties"])), sparkline(vals)))
        return ('<div class="scroll"><table class="data sortable"><thead><tr><th scope="col">State</th>'
                '<th scope="col" class="n">%d survey, $/acre</th><th scope="col" class="n">Change from %d</th>'
                '<th scope="col" class="n">%d census, $/acre</th><th scope="col" class="n">Change from %d</th>'
                '<th scope="col" class="n">Counties</th><th scope="col" class="nosort">20-year trend</th></tr></thead><tbody>%s</tbody></table></div>'
                % (sy or 0, (sy or 1) - 1, cy, py or 0, "".join(rows)))

    # ------------------------------------------------------------------ other pages
    def states_index(self):
        ix = self.ix
        crumbs, crumb_ld = self.crumbs([("States", "/states/")])
        groups = []
        for st in sorted(ix.states.values(), key=lambda s: s["name"]):
            if not st["counties"] or st["code"] == "DC":
                continue
            links = " · ".join(self.county_link(ix.counties[f]) for f in st["counties"])
            groups.append('<section class="stategroup"><h2><a href="%s">%s</a></h2><p>%s</p></section>' % (
                self.u(ix.state_path(st)), esc(st["name"]), links))
        dc = ix.states.get("DC")
        if dc and dc["counties"]:
            groups.append('<section class="stategroup"><h2><a href="%s">District of Columbia</a></h2><p>Residential land values only.</p></section>'
                          % self.u(ix.state_path(dc)))
        body = [crumbs, "<h1>Land prices by state and county</h1>",
                '<p class="lede">Every state and county in the index. State pages have a county map and a sortable table.</p>',
                self.search_box(), "<section><h2>State summary</h2>%s</section>" % self.states_table(), "".join(groups)]
        desc = "Browse land prices per acre for every US state and %s counties: USDA farm real estate values, cash rents and FHFA residential land values." % num(len(ix.counties))
        return self.layout("Land prices by state and county | %s" % config.SITE_SHORT, desc, "/states/", "".join(body), [crumb_ld], wide=True)

    def rankings(self):
        ix = self.ix
        cy, py = ix.census_year, ix.prev_census_year
        crumbs, crumb_ld = self.crumbs([("Rankings", "/rankings/")])
        big = self.big_counties()
        top = sorted(big, key=lambda c: -c["obs"][cy])[:50]
        low = sorted(big, key=lambda c: c["obs"][cy])[:50]
        movers = [c for c in big if c.get("census_chg") is not None]
        up = sorted(movers, key=lambda c: -c["census_chg"])[:25]
        down = sorted(movers, key=lambda c: c["census_chg"])[:25]
        allc = sorted((c for c in ix.counties.values() if c["obs"].get(cy)), key=lambda c: -c["obs"][cy])[:25]
        t = lambda cs: self.county_table([c["fips"] for c in cs], with_state=True, rank=True)  # noqa: E731
        body = [
            crumbs, "<h1>County land price rankings</h1>",
            '<p class="lede">Counties ranked by USDA\'s %d Census of Agriculture value of farm land and buildings per acre. '
            'Unless stated, lists include only the %s counties with at least %s acres in farms, because a handful of city farms can swing a small county\'s average.</p>'
            % (cy, num(len(big)), num(MIN_ACRES)),
            '<nav class="toc" aria-label="On this page"><a href="#highest">Highest</a> · <a href="#lowest">Lowest</a> · <a href="#up">Largest increases</a> · '
            '<a href="#down">Largest decreases</a> · <a href="#all">Highest, any size</a></nav>',
            '<section id="highest"><h2>Highest value per acre</h2>%s</section>' % t(top),
            '<section id="lowest"><h2>Lowest value per acre</h2>%s</section>' % t(low),
            '<section id="up"><h2>Largest increases, %d to %d</h2><p>Change between the two most recent censuses. Both figures are observations.</p>%s</section>' % (py, cy, t(up)),
            '<section id="down"><h2>Largest decreases, %d to %d</h2>%s</section>' % (py, cy, t(down)),
            '<section id="all"><h2>Highest value per acre, counties of any size</h2><p>With no minimum acreage the list is led by urban counties '
            'where a few small farms sit on very expensive land. Check the acres in farms before reading much into these.</p>%s</section>' % t(allc),
            self.reading_notes(),
        ]
        desc = "Which US counties have the highest and lowest farm land values per acre, and where values changed most between the %d and %d USDA censuses." % (py, cy)
        return self.layout("County land price rankings: highest and lowest per acre | %s" % config.SITE_SHORT, desc, "/rankings/",
                           "".join(body), [crumb_ld], wide=True)

    def methodology(self):
        ix = self.ix
        cy, py, sy = ix.census_year, ix.prev_census_year, ix.survey_year
        crumbs, crumb_ld = self.crumbs([("Method", "/methodology/")])
        n_obs = sum(1 for c in ix.counties.values() if c["obs"].get(cy))
        n_est = sum(1 for c in ix.counties.values() if c.get("estimate"))
        n_panel = len(ix.fhfa_county)
        n_cs = len(ix.fhfa_cs)
        fy0, fy1 = (ix.fhfa_years[0], ix.fhfa_year) if ix.fhfa_years else (0, 0)
        ex = ix.counties.get("19169") or next(c for c in ix.counties.values() if c.get("estimate"))
        ex_st = ix.states[ex["state"]]
        e = ex["estimate"]
        body = [crumbs, "<h1>How the index is built</h1>", """
<p class="lede">The index answers one question: roughly what is an acre of land worth in each US county, and how has that changed?
It uses only official statistics, says which numbers are observed and which are estimated, and publishes every input.</p>

<section><h2>The sources</h2>
<table class="data"><thead><tr><th scope="col">Source</th><th scope="col">What it measures</th><th scope="col">Detail</th><th scope="col">How often</th></tr></thead><tbody>
<tr><th scope="row">USDA Census of Agriculture</th><td>Estimated market value of farm land and buildings, per acre</td><td>County</td><td>Every five years (%(cy)d is the latest)</td></tr>
<tr><th scope="row">USDA Land Values survey</th><td>Farm real estate, cropland and pasture value per acre</td><td>State (48 contiguous states)</td><td>Every year, published in August</td></tr>
<tr><th scope="row">USDA Cash Rents survey</th><td>Rent paid per acre for cropland and pasture</td><td>County and state</td><td>Most years</td></tr>
<tr><th scope="row">FHFA Working Paper 19-01 data</th><td>Value of the land under single-family homes</td><td>County (%(n_panel)s with yearly figures, %(n_cs)s with a pooled figure)</td><td>%(fy0)d to %(fy1)d; updated irregularly</td></tr>
</tbody></table>
<p>All USDA series come from one public file, the National Agricultural Statistics Service's Quick Stats "economics" bulk download.
FHFA's data is the workbook attached to its working paper. FHFA describes its series as experimental.</p></section>

<section><h2>What "farm real estate value" means</h2>
<p>In the census, each farm operator estimates what their land and buildings would sell for. USDA adds those up for the county and divides by the
acres in farms. So the county figure is an average over cropland, pasture, woodland and farmsteads together, buildings included.
It is the closest thing to an official rural land price that exists for every county, but it is not a price for bare land, and it is not a sale price.</p>
<p>In %(cy)d USDA published a value for %(n_obs)s counties and county-equivalents. It withholds a figure when publishing it could reveal a single farm's answer.</p></section>

<section><h2>From census values to an annual series</h2>
<ol>
<li><strong>Census years are observations.</strong> The county's published value is used as is.</li>
<li><strong>Years between two censuses are estimates.</strong> The county follows its state's annual survey from one census to the next.
If the county rose faster or slower than its state over those five years, that difference is spread evenly across them, so the line still passes through both census values.</li>
<li><strong>Years after the latest census are estimates.</strong> The %(cy)d value is multiplied by the change in the state's survey value since %(cy)d.
This assumes the county has moved with its state. It is the weakest part of the series, and it is replaced when the next census is published.</li>
</ol>
<p>Example: %(ex_name)s was %(ex_obs)s per acre in the %(cy)d census. %(ex_state)s's survey value went from %(s0)s in %(cy)d to %(s1)s in %(ey)d, a change of %(schg)s.
The %(ey)d estimate is %(ex_obs)s &times; %(s1)s &divide; %(s0)s, rounded to three significant figures: %(ex_est)s.</p>
<p>%(n_est)s counties have an estimate for %(sy)d. There is none where USDA withheld the %(cy)d value, or in Alaska and Hawaii, which the annual survey does not cover.
Estimates are rounded to three significant figures so they do not look more exact than they are.</p></section>

<section><h2>The index level</h2>
<p>The national index level is USDA's US farm real estate value per acre divided by its %(base)d value, times 100. %(base)d is the first census year in USDA's bulk file with county land values.
County pages show dollars, which are easier to check against the sources. All figures are in the dollars of their own year: nothing is adjusted for inflation.</p></section>

<section><h2>Rankings</h2>
<p>Counties are ranked by their %(cy)d census value, because that is the latest year every county was observed. Ranking tables leave out counties with
fewer than %(min_acres)s acres in farms unless they say otherwise: in a city county, a few small farms on expensive land produce an average that describes almost nothing.</p></section>

<section><h2>Residential land (FHFA)</h2>
<p>FHFA's economists estimate land value by subtracting the depreciated cost of the house from the appraised value of the property, across millions of appraisals.
"As is" values describe the lots that exist in the county; the "standardized" value prices a quarter-acre lot so that places can be compared.
Residential lots have roads, utilities and permission to build, so an acre of them is worth many times an acre of farmland nearby.
The two series are shown side by side, never blended.</p></section>

<section><h2>Limits you should know</h2>
<ul class="notes">
<li>County figures are averages. A parcel's price depends on soil, water, access, improvements, zoning and distance to town.</li>
<li>Census values are operators' own estimates and include buildings.</li>
<li>Estimates assume a county tracked its state. Counties near growing cities, or with different crops from the rest of the state, often did not.</li>
<li>Small counties have noisy figures. USDA's coefficient of variation is shown where it was published.</li>
<li>Alaska is reported by USDA in five multi-borough areas, Connecticut by its eight historical counties.</li>
<li>Nothing here is investment advice or an appraisal, and past changes say nothing certain about future ones.</li>
</ul></section>

<section><h2>Updates and corrections</h2>
<p>A scheduled job checks both sources every month, and every week from August to October, when USDA publishes its land value and cash rent reports.
It rebuilds the site when either source has published something new, and keeps the last good data if a source cannot be reached.
The current state of each source is on the <a href="%(data)s">data page</a>. The code that does all of this is public. If a number here disagrees with USDA or FHFA,
please <a href="%(issues)s" rel="noopener">open an issue</a> with the county and the source figure.</p></section>
""" % {
            "cy": cy, "sy": sy, "n_obs": num(n_obs), "n_est": num(n_est), "n_panel": num(n_panel), "n_cs": num(n_cs), "fy0": fy0, "fy1": fy1,
            "ex_name": esc(ex["label"]), "ex_obs": money(ex["obs"][e[2]]), "ex_state": esc(ex["state_name"]),
            "s0": money(ex_st["series"][e[2]]), "s1": money(ex_st["series"][e[0]]), "ey": e[0],
            "schg": pct(pct_change(ex_st["series"][e[0]], ex_st["series"][e[2]])), "ex_est": money(e[1]),
            "base": FIRST_INDEX_YEAR, "min_acres": num(MIN_ACRES), "data": self.u("/data/"), "issues": esc(config.REPO_URL + "/issues"),
        }]
        desc = "How the US County Land Index turns USDA census and survey data and FHFA land price data into land values per acre for every county, and what the numbers cannot tell you."
        return self.layout("Method: how county land values are estimated | %s" % config.SITE_SHORT, desc, "/methodology/", "".join(body), [crumb_ld])

    def data_page(self, files):
        """files: [(path, description, rows)] for the national downloads."""
        ix = self.ix
        crumbs, crumb_ld = self.crumbs([("Data", "/data/")])
        rows = "".join('<tr><th scope="row"><a href="%s">%s</a></th><td>%s</td><td class="n">%s</td></tr>' % (
            self.u(p), esc(p.rsplit("/", 1)[-1]), d, num(n)) for p, d, n in files)
        srows = []
        for key in sorted(ix.status.get("sources", {})):
            s = ix.status["sources"][key]
            latest = ", ".join("%s %s" % (k.replace("latest_", "").replace("_", " "), v) for k, v in sorted(s.items()) if k.startswith("latest_") and v)
            srows.append('<tr><th scope="row">%s</th><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                esc(s.get("label", key)), "reachable" if s.get("ok") else "kept on last good data", esc(s.get("checked", "")),
                esc(s.get("changed", "")), esc(latest or s.get("version", ""))))
        ex = ix.counties.get("19169") or next(iter(ix.counties.values()))
        body = [crumbs, "<h1>Data and API</h1>",
                '<p class="lede">Everything on this site is a file you can download. No key, no sign-up, no rate limit beyond ordinary politeness.</p>',
                '<section><h2>Downloads</h2><div class="scroll"><table class="data"><thead><tr><th scope="col">File</th><th scope="col">Contents</th>'
                '<th scope="col" class="n">Rows</th></tr></thead><tbody>%s</tbody></table></div>'
                '<p>Per-state and per-county files: <code>%s</code> and <code>%s</code>, where the county code is the five-digit FIPS code. '
                'The same files are mirrored in the <a href="%s" rel="noopener">GitHub repository</a> under <code>data/</code>, with their full change history.</p></section>'
                % (rows, esc(self.absu("/data/state/ia.csv")), esc(self.absu("/data/county/19169.csv")), esc(config.REPO_URL + "/tree/main/data")),
                '<section><h2>JSON</h2><p>One static JSON document per county: <code>%s</code>. Example: <a href="%s">%s</a>. '
                'The list of every county with its code, page and latest values is <a href="%s">counties.json</a>. '
                'Files are served with open CORS headers by GitHub Pages, so a browser script on another site can read them.</p></section>'
                % (esc(self.absu("/api/county/{fips}.json")), self.u("/api/county/%s.json" % ex["fips"]), esc(ex["label"]), self.u("/api/counties.json")),
                '<section><h2>Embed</h2><p>Each county page has a snippet for a small live card. The pattern is '
                '<code>&lt;iframe src="%s"&gt;</code>.</p></section>' % esc(self.absu("/embed/?fips=19169")),
                '<section><h2>Source status</h2><div class="scroll"><table class="data"><thead><tr><th scope="col">Source</th><th scope="col">Last check</th>'
                '<th scope="col">Checked on</th><th scope="col">Data last changed</th><th scope="col">Latest</th></tr></thead><tbody>%s</tbody></table></div>'
                '<p>Machine-readable: <a href="%s">status.json</a>.</p></section>' % ("".join(srows), self.u("/data/status.json")),
                '<section><h2>Licence</h2><p>USDA and FHFA data are works of the US government and are in the public domain. '
                'The estimates, joins and files made here are dedicated to the public domain under '
                '<a href="https://creativecommons.org/publicdomain/zero/1.0/" rel="noopener license">CC0 1.0</a>. '
                'County outlines come from the US Census Bureau\'s cartographic boundary files. '
                'Credit is welcome and not required: "US County Land Index, from USDA NASS and FHFA data".</p></section>',
                '<section><h2>Columns</h2><ul class="notes">'
                '<li><code>kind</code>: <code>census</code> is a USDA Census of Agriculture observation; <code>interpolated</code> is an estimate between two censuses; '
                '<code>estimate</code> is an estimate after the latest census.</li>'
                '<li><code>value_per_acre</code>: farm land and buildings, US dollars of that year.</li>'
                '<li><code>cv_pct</code>: USDA\'s coefficient of variation for the census value, in percent.</li>'
                '<li><code>suppressed</code>: 1 where USDA withheld the value.</li>'
                '<li>FHFA columns: <code>land_value_per_acre</code> is "as is"; <code>land_value_quarter_acre_std</code> is the standardized quarter-acre lot; '
                '<code>land_share</code> is land value as a share of property value.</li></ul></section>']
        desc = "Download the US County Land Index: CSV and JSON files of USDA farm real estate values, cash rents and FHFA residential land values for every county. Public domain."
        ld = self.dataset_ld("US County Land Index data files", desc, "/data/", "United States", [("text/csv", p) for p, _, _ in files])
        return self.layout("Data downloads and API | %s" % config.SITE_SHORT, desc, "/data/", "".join(body), [crumb_ld, ld])

    def about(self):
        crumbs, crumb_ld = self.crumbs([("About", "/about/")])
        support = ""
        if config.SUPPORT_URL:
            support = ('<section><h2>Support</h2><p>The index is free and carries no advertising. If it is useful to you, you can '
                       '<a href="%s" rel="noopener sponsored">support its upkeep</a>.</p></section>') % esc(config.SUPPORT_URL)
        analytics = ("This site uses GoatCounter to count page views without cookies and without tracking individuals."
                     if config.GOATCOUNTER else "This site sets no cookies and runs no analytics or advertising scripts.")
        body = [crumbs, "<h1>About the index</h1>", """
<p class="lede">The US County Land Index is a free, open reference for land values per acre in every US county, made entirely from public statistics.</p>
<section><h2>What it is</h2><p>A statistical index: a consistent way to look up, compare and download official land value figures.
It was built because the underlying numbers are public but scattered across large files that are awkward to use.</p></section>
<section><h2>What it is not</h2><p>It is not a financial product and offers nothing to buy. It gives no investment advice and makes no forecast.
It is not an appraisal: no figure here describes a particular parcel. It is not affiliated with USDA, FHFA or any government agency.</p></section>
<section><h2>How it runs</h2><p>The site is generated by open-source code on a schedule. Every month, and every week in USDA's August-to-October release season,
it checks USDA and FHFA for new releases and rebuilds if anything changed. Every week it tests itself and its links. No one edits the numbers by hand. Details are on the <a href="%s">method page</a>.</p></section>
<section><h2>Corrections and contact</h2><p>Found a figure that disagrees with its source? <a href="%s" rel="noopener">Open an issue on GitHub</a>.
That is also the place for questions and requests.</p></section>
<section><h2>Privacy</h2><p>%s The search box works in your browser and sends nothing anywhere.</p></section>%s
""" % (self.u("/methodology/"), esc(config.REPO_URL + "/issues"), analytics, support)]
        desc = "About the US County Land Index: a free, open, automatically updated reference for land values per acre, built from USDA and FHFA statistics. Not investment advice."
        return self.layout("About | %s" % config.SITE_SHORT, desc, "/about/", "".join(body), [crumb_ld])

    def embed(self):
        """One static page that renders a card for any county from its JSON. Not indexed: it has no content of its own."""
        return (
            '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta name="robots" content="noindex"><title>County land price card | %s</title>'
            '<link rel="canonical" href="%s"><link rel="icon" href="%s" type="image/svg+xml"><link rel="stylesheet" href="%s"></head>'
            '<body class="embed" data-base="%s"><div id="card" class="card"><p>Loading…</p></div>'
            '<noscript><p>This card needs JavaScript. <a href="%s" target="_top">Open the index</a>.</p></noscript>'
            '<script src="%s" defer></script></body></html>'
        ) % (esc(config.SITE_SHORT), esc(self.absu("/embed/")), self.u("/assets/favicon.svg"), self.u("/assets/style.css"),
             esc(self.base), self.absu("/"), self.u("/assets/embed.js"))

    def not_found(self):
        body = ('<h1>Page not found</h1><p class="lede">That address is not part of the index. County pages live under their state, '
                'for example <a href="%s">/iowa/story-county/</a>.</p>%s<p><a href="%s">Browse every state and county</a></p>'
                % (self.u("/iowa/story-county/"), self.search_box(), self.u("/states/")))
        return self.layout("Page not found | %s" % config.SITE_SHORT, "This page does not exist.", "/404.html", body, noindex=True)


def pct_change(new, old):
    if new is None or old is None or old == 0:
        return None
    return (new / old - 1.0) * 100.0
