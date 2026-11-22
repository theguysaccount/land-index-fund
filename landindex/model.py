"""Load data/ and compute the index: one record per county, state and the nation.

Method in one paragraph (the public version is the /methodology/ page):
USDA's Census of Agriculture gives each county an average market value of farm land and buildings per acre every
five years. USDA's annual survey gives each state a value per acre every year. A county's series is its census
values, joined between census years by the state's annual movement (the county's own gap to the state is closed
smoothly across the five years), and carried past the last census by the state's movement alone. Census years
are observations. Every other year is an estimate and is labelled as one everywhere.
"""
import json
import os
import re
import unicodedata

from . import config, sources

STATES = [  # (FIPS, postal code, name)
    ("01", "AL", "Alabama"), ("02", "AK", "Alaska"), ("04", "AZ", "Arizona"), ("05", "AR", "Arkansas"),
    ("06", "CA", "California"), ("08", "CO", "Colorado"), ("09", "CT", "Connecticut"), ("10", "DE", "Delaware"),
    ("11", "DC", "District of Columbia"), ("12", "FL", "Florida"), ("13", "GA", "Georgia"), ("15", "HI", "Hawaii"),
    ("16", "ID", "Idaho"), ("17", "IL", "Illinois"), ("18", "IN", "Indiana"), ("19", "IA", "Iowa"),
    ("20", "KS", "Kansas"), ("21", "KY", "Kentucky"), ("22", "LA", "Louisiana"), ("23", "ME", "Maine"),
    ("24", "MD", "Maryland"), ("25", "MA", "Massachusetts"), ("26", "MI", "Michigan"), ("27", "MN", "Minnesota"),
    ("28", "MS", "Mississippi"), ("29", "MO", "Missouri"), ("30", "MT", "Montana"), ("31", "NE", "Nebraska"),
    ("32", "NV", "Nevada"), ("33", "NH", "New Hampshire"), ("34", "NJ", "New Jersey"), ("35", "NM", "New Mexico"),
    ("36", "NY", "New York"), ("37", "NC", "North Carolina"), ("38", "ND", "North Dakota"), ("39", "OH", "Ohio"),
    ("40", "OK", "Oklahoma"), ("41", "OR", "Oregon"), ("42", "PA", "Pennsylvania"), ("44", "RI", "Rhode Island"),
    ("45", "SC", "South Carolina"), ("46", "SD", "South Dakota"), ("47", "TN", "Tennessee"), ("48", "TX", "Texas"),
    ("49", "UT", "Utah"), ("50", "VT", "Vermont"), ("51", "VA", "Virginia"), ("53", "WA", "Washington"),
    ("54", "WV", "West Virginia"), ("55", "WI", "Wisconsin"), ("56", "WY", "Wyoming"),
]
STATE_BY_FIPS = {f: (a, n) for f, a, n in STATES}
# USDA reports Alaska's farmland for five multi-borough areas, coded with the main borough's number.
ALASKA_AREAS = {"02010": "Aleutian Islands Area", "02020": "Anchorage Area", "02090": "Fairbanks Area",
                "02110": "Juneau Area", "02122": "Kenai Peninsula Area"}
FIRST_INDEX_YEAR = 1997  # the first Census of Agriculture in the bulk file with county land values


def slugify(text):
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    t = t.replace("'", "").replace(".", "")
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def sig(value, digits=3):
    """Round to `digits` significant figures; an estimate should not look more exact than its inputs."""
    if value is None:
        return None
    if value == 0:
        return 0
    from math import floor, log10
    mag = digits - 1 - int(floor(log10(abs(value))))
    r = round(value, mag)
    return int(r) if mag <= 0 else r


def _f(text):
    try:
        return float(text) if text not in (None, "") else None
    except ValueError:
        return None


def _i(text):
    v = _f(text)
    return int(v) if v is not None else None


def pct(new, old):
    if new is None or old is None or old == 0:
        return None
    return (new / old - 1.0) * 100.0


def county_series(census, state_survey, last_year):
    """Annual series for one county.

    census        {year: value} of non-suppressed census observations
    state_survey  {year: value} of the state's annual survey values (may be empty)
    Returns [(year, value, kind)] with kind 'census', 'interpolated' or 'estimate', from the first observation
    to `last_year`. Years the state series cannot support are left out.
    """
    obs = sorted(census)
    out = []
    if not obs:
        return out
    for a, b in zip(obs, obs[1:]):
        out.append((a, census[a], "census"))
        sa, sb = state_survey.get(a), state_survey.get(b)
        if not sa or not sb:
            continue
        gap = (census[b] / census[a]) / (sb / sa)  # how far the county outran or lagged its state
        for t in range(a + 1, b):
            st = state_survey.get(t)
            if st:
                out.append((t, sig(census[a] * (st / sa) * gap ** ((t - a) / float(b - a))), "interpolated"))
    last = obs[-1]
    out.append((last, census[last], "census"))
    sl = state_survey.get(last)
    if sl:
        for t in range(last + 1, last_year + 1):
            st = state_survey.get(t)
            if st:
                out.append((t, sig(census[last] * st / sl), "estimate"))
    return out


class Index(object):
    """Everything the site renders, computed from data/."""

    def __init__(self, data_dir=None):
        self.data_dir = data_dir or config.DATA
        self.status = sources.load_status(self.data_dir)
        self._load_geo()
        self._load_usda()
        self._load_fhfa()
        self._build()

    # ------------------------------------------------------------------ loading
    def _load_geo(self):
        self.geo, self.geo_states, self.geo_meta = {}, {}, {}
        path = os.path.join(self.data_dir, "geo", "counties.json")
        if os.path.exists(path):
            with open(path) as fh:
                g = json.load(fh)
            self.geo_meta = g.get("meta", {})
            self.geo = {c["f"]: c for c in g["counties"]}
        path = os.path.join(self.data_dir, "geo", "states.json")
        if os.path.exists(path):
            with open(path) as fh:
                self.geo_states = {s["s"]: s for s in json.load(fh)["states"]}

    def _load_usda(self):
        rd = lambda name: sources.read_csv(name, self.data_dir)  # noqa: E731
        self.county_census = {}
        for r in rd("usda_county_land_value.csv"):
            self.county_census.setdefault(r["fips"], {})[int(r["year"])] = {
                "value": _f(r["value_per_acre"]), "cv": _f(r["cv_pct"]), "suppressed": r["suppressed"] == "1",
                "acres": _i(r["acres_in_farms"]), "farms": _i(r["farms"]), "nass_name": r["county_name"]}
        self.state_census = {}
        for r in rd("usda_census_state_land_value.csv"):
            self.state_census.setdefault(r["state"], {})[int(r["year"])] = {
                "value": _f(r["value_per_acre"]), "acres": _i(r["acres_in_farms"]), "farms": _i(r["farms"])}
        self.state_survey = {}
        for r in rd("usda_state_land_value.csv"):
            self.state_survey.setdefault(r["state"], {})[int(r["year"])] = {
                "all": _f(r["farm_real_estate"]), "cropland": _f(r["cropland"]), "pasture": _f(r["pasture"])}
        self.county_rent = {}
        for r in rd("usda_county_cash_rent.csv"):
            self.county_rent.setdefault(r["fips"], {})[int(r["year"])] = {
                "nonirr": _f(r["cropland_nonirrigated"]), "irr": _f(r["cropland_irrigated"]),
                "pasture": _f(r["pasture"])}
        self.state_rent = {}
        for r in rd("usda_state_cash_rent.csv"):
            self.state_rent.setdefault(r["state"], {})[int(r["year"])] = {
                "cropland": _f(r["cropland"]), "nonirr": _f(r["cropland_nonirrigated"]),
                "irr": _f(r["cropland_irrigated"]), "pasture": _f(r["pasture"])}

    def _load_fhfa(self):
        rd = lambda name: sources.read_csv(name, self.data_dir)  # noqa: E731

        def vals(r):
            return {"per_acre": _f(r["land_value_per_acre"]), "quarter": _f(r["land_value_quarter_acre_std"]),
                    "share": _f(r["land_share"]), "property": _f(r["property_value"])}
        self.fhfa_county = {}
        for r in rd("fhfa_county_panel.csv"):
            self.fhfa_county.setdefault(r["fips"], {})[int(r["year"])] = vals(r)
        self.fhfa_cs = {}
        for r in rd("fhfa_county_cross_section.csv"):
            v = vals(r)
            v.update({"lot": _f(r["lot_size_sqft"]), "name": r["county_name"], "state_name": r["state_name"]})
            self.fhfa_cs[r["fips"]] = v
        self.fhfa_state = {}
        for r in rd("fhfa_state_panel.csv"):
            self.fhfa_state.setdefault(r["state"], {})[int(r["year"])] = vals(r)
        self.fhfa_nation = {int(r["year"]): vals(r) for r in rd("fhfa_nation_panel.csv")}

    # ------------------------------------------------------------------ computing
    def _build(self):
        us_survey = {y: v["all"] for y, v in self.state_survey.get("US", {}).items() if v["all"]}
        census_years = sorted({y for c in self.county_census.values() for y in c})
        self.census_years = census_years
        self.census_year = census_years[-1] if census_years else None
        self.prev_census_year = census_years[-2] if len(census_years) > 1 else None
        self.survey_year = max(us_survey) if us_survey else None
        self.fhfa_years = sorted(self.fhfa_nation)
        self.fhfa_year = self.fhfa_years[-1] if self.fhfa_years else None

        self.states = {}
        for sf, alpha, name in STATES:
            survey = self.state_survey.get(alpha, {})
            series = {y: v["all"] for y, v in survey.items() if v["all"]}
            census = self.state_census.get(alpha, {})
            latest = max(series) if series else None
            st = {
                "fips": sf, "code": alpha, "name": name, "slug": slugify(name), "survey": survey, "series": series,
                "census": census, "latest_year": latest, "latest": series.get(latest) if latest else None,
                "rent": self.state_rent.get(alpha, {}), "fhfa": self.fhfa_state.get(alpha, {}), "counties": [],
            }
            if latest:
                st["chg1"] = pct(series.get(latest), series.get(latest - 1))
                st["chg5"] = pct(series.get(latest), series.get(latest - 5))
                st["chg10"] = pct(series.get(latest), series.get(latest - 10))
            cy, py = self.census_year, self.prev_census_year
            st["census_value"] = (census.get(cy) or {}).get("value")
            st["census_chg"] = pct(st["census_value"], (census.get(py) or {}).get("value")) if py else None
            self.states[alpha] = st

        us_census = self.state_census.get("US", {})
        self.us = {
            "survey": self.state_survey.get("US", {}), "series": us_survey, "census": us_census,
            "latest_year": self.survey_year, "latest": us_survey.get(self.survey_year),
            "chg1": pct(us_survey.get(self.survey_year), us_survey.get((self.survey_year or 0) - 1)),
            "chg5": pct(us_survey.get(self.survey_year), us_survey.get((self.survey_year or 0) - 5)),
            "chg10": pct(us_survey.get(self.survey_year), us_survey.get((self.survey_year or 0) - 10)),
            "rent": self.state_rent.get("US", {}), "fhfa": self.fhfa_nation,
        }
        base = us_survey.get(FIRST_INDEX_YEAR)
        self.us["index"] = {y: round(100.0 * v / base, 1) for y, v in us_survey.items()
                            if base and y >= FIRST_INDEX_YEAR}

        self.counties = {}
        ids = set(self.fhfa_cs) | set(self.fhfa_county)
        for fips, years in self.county_census.items():
            if any(v["value"] for v in years.values()):
                ids.add(fips)
        for fips in sorted(ids):
            sf = fips[:2]
            if sf not in STATE_BY_FIPS:
                continue
            alpha, state_name = STATE_BY_FIPS[sf]
            geo = self.geo.get(fips)
            census_rows = self.county_census.get(fips, {})
            usda_area = ALASKA_AREAS.get(fips) if census_rows else None
            if geo:
                name = geo["n"]
                if name.endswith(" city"):
                    name = name[:-5] + " City"
            elif usda_area:
                name = usda_area
            elif fips in self.fhfa_cs:
                name = self.fhfa_cs[fips]["name"]
            else:
                nass = next(iter(census_rows.values()))["nass_name"] if census_rows else fips
                name = nass.title() + " County"
            obs = {y: v["value"] for y, v in census_rows.items() if v["value"]}
            st = self.states[alpha]
            series = county_series(obs, st["series"], self.survey_year or 0)
            c = {
                "fips": fips, "name": name, "state": alpha, "state_name": state_name, "slug": slugify(name),
                "usda_area": usda_area, "census": census_rows, "obs": obs, "series": series,
                "rent": self.county_rent.get(fips, {}), "fhfa": self.fhfa_county.get(fips, {}),
                "fhfa_cs": self.fhfa_cs.get(fips), "area_sq_mi": geo["a"] if geo else None,
                "has_shape": bool(geo), "neighbors": [],
            }
            c["label"] = "%s, %s" % (name, state_name) if name != state_name else name
            if obs:
                last = max(obs)
                c["latest_obs"] = (last, obs[last])
                c["first_obs"] = (min(obs), obs[min(obs)])
                prev = [y for y in sorted(obs) if y < last]
                if prev and self.prev_census_year and last == self.census_year and prev[-1] == self.prev_census_year:
                    c["census_chg"] = pct(obs[last], obs[prev[-1]])
                if min(obs) < last:
                    c["long_chg"] = pct(obs[last], obs[min(obs)])
                sc = (st["census"].get(last) or {}).get("value")
                c["vs_state"] = pct(obs[last], sc)
                uc = (us_census.get(last) or {}).get("value")
                c["vs_us"] = pct(obs[last], uc)
            est = [s for s in series if s[2] == "estimate"]
            if est:
                c["estimate"] = (est[-1][0], est[-1][1], max(obs))
            if series:
                c["current"] = (series[-1][0], series[-1][1], series[-1][2])
                first = series[0]
                c["index"] = {y: round(100.0 * v / first[1], 1) for y, v, _ in series}
                c["index_base"] = first[0]
            st["counties"].append(fips)
            self.counties[fips] = c

        for c in self.counties.values():
            geo = self.geo.get(c["fips"])
            if geo:
                c["neighbors"] = [n for n in geo.get("nb", []) if n in self.counties]

        # Slugs must be unique inside a state: they are the page addresses.
        for st in self.states.values():
            seen = {}
            for fips in st["counties"]:
                c = self.counties[fips]
                if c["slug"] in seen:
                    c["slug"] = "%s-%s" % (c["slug"], fips)
                seen[c["slug"]] = fips
            st["counties"].sort(key=lambda f: self.counties[f]["name"])

        self._rank()

    def _rank(self):
        cy = self.census_year
        ranked = sorted((c for c in self.counties.values() if c["obs"].get(cy)), key=lambda c: -c["obs"][cy])
        self.ranked = [c["fips"] for c in ranked]
        for i, c in enumerate(ranked):
            c["rank_us"] = i + 1
            c["n_us"] = len(ranked)
        for st in self.states.values():
            inside = [c for c in ranked if c["state"] == st["code"]]
            for i, c in enumerate(inside):
                c["rank_state"] = i + 1
                c["n_state"] = len(inside)
            st["n_ranked"] = len(inside)
        states = sorted((s for s in self.states.values() if s.get("census_value")), key=lambda s: -s["census_value"])
        for i, s in enumerate(states):
            s["rank_us"] = i + 1
            s["n_us"] = len(states)

    # ------------------------------------------------------------------ helpers for pages
    def county_path(self, c):
        st = self.states[c["state"]]
        if c["state"] == "DC":
            return "/%s/" % st["slug"]
        return "/%s/%s/" % (st["slug"], c["slug"])

    def state_path(self, st):
        return "/%s/" % st["slug"]

    def county_json(self, c):
        """Public JSON for one county: the same numbers the page shows."""
        out = {
            "fips": c["fips"], "name": c["name"], "state": c["state"], "state_name": c["state_name"],
            "url": config.BASE_URL + self.county_path(c),
            "usda_farm_real_estate_per_acre": [{"year": y, "value": v, "kind": k} for y, v, k in c["series"]],
            "usda_census": [{"year": y, "value_per_acre": r["value"], "suppressed": r["suppressed"],
                             "cv_pct": r["cv"], "acres_in_farms": r["acres"], "farms": r["farms"]}
                            for y, r in sorted(c["census"].items())],
            "usda_cash_rent_per_acre": [{"year": y, "cropland_nonirrigated": r["nonirr"],
                                         "cropland_irrigated": r["irr"], "pasture": r["pasture"]}
                                        for y, r in sorted(c["rent"].items())],
            "fhfa_residential_land": [{"year": y, "land_value_per_acre": r["per_acre"],
                                       "land_value_quarter_acre_standardized": r["quarter"],
                                       "land_share_of_property_value": r["share"]}
                                      for y, r in sorted(c["fhfa"].items())],
            "notes": {
                "kind": "census = USDA Census of Agriculture observation; interpolated and estimate = modelled "
                        "from the state's annual USDA survey (see methodology)",
                "methodology": config.BASE_URL + "/methodology/",
                "not_investment_advice": True,
            },
        }
        if c.get("usda_area"):
            out["usda_area"] = c["usda_area"]
        if c.get("fhfa_cs"):
            cs = c["fhfa_cs"]
            out["fhfa_pooled_cross_section"] = {"land_value_per_acre": cs["per_acre"],
                                                "land_value_quarter_acre_standardized": cs["quarter"],
                                                "land_share_of_property_value": cs["share"],
                                                "lot_size_sqft": cs["lot"]}
        return out
