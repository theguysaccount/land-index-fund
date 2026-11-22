"""Fetch and extract the two public sources behind the index.

USDA NASS    Quick Stats bulk file "qs.economics_YYYYMMDD.txt.gz" (no key needed). One file holds every series
             used here: Census of Agriculture county land values, the annual state land values survey and the
             county cash rents survey.
FHFA         "The Price of Residential Land" workbook attached to Working Paper 19-01 (experimental).

Each source is fetched, parsed and validated on its own. A source that fails keeps its last good extract in
data/ and is reported in data/status.json; it never takes the other source down with it.

    python3 -m landindex.sources check      # are the sources reachable, and what do they offer now?
"""
import csv
import gzip
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config
from .xlsx import Workbook

NASS_LISTING = "https://www.nass.usda.gov/datasets"
FHFA_PAGE = "https://www.fhfa.gov/research/papers/wp1901"

LAND_VALUE = "AG LAND, INCL BUILDINGS - ASSET VALUE, MEASURED IN $ / ACRE"
CROPLAND_VALUE = "AG LAND, CROPLAND - ASSET VALUE, MEASURED IN $ / ACRE"
PASTURE_VALUE = "AG LAND, PASTURELAND - ASSET VALUE, MEASURED IN $ / ACRE"
ACRES = "FARM OPERATIONS - ACRES OPERATED"
FARMS = "FARM OPERATIONS - NUMBER OF OPERATIONS"
RENT_NONIRR = "RENT, CASH, CROPLAND, NON-IRRIGATED - EXPENSE, MEASURED IN $ / ACRE"
RENT_IRR = "RENT, CASH, CROPLAND, IRRIGATED - EXPENSE, MEASURED IN $ / ACRE"
RENT_PASTURE = "RENT, CASH, PASTURELAND - EXPENSE, MEASURED IN $ / ACRE"
RENT_CROPLAND = "RENT, CASH, CROPLAND - EXPENSE, MEASURED IN $ / ACRE"

SURVEY_VALUE_COLS = {LAND_VALUE: "farm_real_estate", CROPLAND_VALUE: "cropland", PASTURE_VALUE: "pasture"}
RENT_COLS = {RENT_CROPLAND: "cropland", RENT_NONIRR: "cropland_nonirrigated", RENT_IRR: "cropland_irrigated",
             RENT_PASTURE: "pasture"}
CENSUS_COLS = {LAND_VALUE: "value_per_acre", ACRES: "acres_in_farms", FARMS: "farms"}
WANTED_COMMODITIES = ("AG LAND", "RENT", "FARM OPERATIONS")

# Files written to data/. The header order is the public CSV layout: change it only with a note in DECISIONS.md.
FILES = {
    "usda_county_land_value.csv": ["fips", "state", "county_name", "year", "value_per_acre", "cv_pct", "suppressed",
                                   "acres_in_farms", "farms"],
    "usda_census_state_land_value.csv": ["state", "year", "value_per_acre", "acres_in_farms", "farms"],
    "usda_state_land_value.csv": ["state", "year", "farm_real_estate", "cropland", "pasture"],
    "usda_county_cash_rent.csv": ["fips", "state", "county_name", "year", "cropland_nonirrigated",
                                  "cropland_irrigated", "pasture"],
    "usda_state_cash_rent.csv": ["state", "year", "cropland", "cropland_nonirrigated", "cropland_irrigated",
                                 "pasture"],
    "fhfa_county_panel.csv": ["fips", "year", "land_value_per_acre", "land_value_quarter_acre_std", "land_share",
                              "property_value", "property_value_std"],
    "fhfa_county_cross_section.csv": ["fips", "state_name", "county_name", "land_value_per_acre",
                                      "land_value_quarter_acre_std", "land_share", "lot_size_sqft", "interior_sqft",
                                      "property_value", "property_value_std"],
    "fhfa_state_panel.csv": ["state", "year", "land_value_per_acre", "land_value_quarter_acre_std", "land_share",
                             "property_value", "property_value_std"],
    "fhfa_nation_panel.csv": ["year", "land_value_per_acre", "land_value_quarter_acre_std", "land_share",
                              "property_value", "property_value_std"],
}
NASS_FILES = [n for n in FILES if n.startswith("usda_")]
FHFA_FILES = [n for n in FILES if n.startswith("fhfa_")]


class SourceError(Exception):
    """A source could not be fetched, parsed or trusted. The caller keeps the last good extract."""


# ---------------------------------------------------------------------------------------------- HTTP

def _request(url, headers=None):
    h = {"User-Agent": config.USER_AGENT, "Accept": "*/*"}
    h.update(headers or {})
    return urllib.request.Request(url, headers=h)


def fetch_text(url, tries=3, timeout=60, pause=8):
    last = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(_request(url), timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:  # network errors, HTTP errors, timeouts
            last = exc
            if attempt + 1 < tries:
                time.sleep(pause * (attempt + 1))
    raise SourceError("could not read %s (%s)" % (url, last))


def head(url, tries=3, timeout=60, pause=8):
    """Size, Last-Modified and ETag of a file, without downloading it."""
    last = None
    for attempt in range(tries):
        try:
            req = _request(url)
            req.get_method = lambda: "HEAD"
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return {"url": url, "bytes": int(resp.headers.get("Content-Length") or 0),
                        "last_modified": resp.headers.get("Last-Modified") or "",
                        "etag": (resp.headers.get("ETag") or "").strip('"')}
        except Exception as exc:
            last = exc
            if attempt + 1 < tries:
                time.sleep(pause * (attempt + 1))
    raise SourceError("could not reach %s (%s)" % (url, last))


def download(url, dest, expect_bytes=0, tries=5, timeout=120, pause=15, log=print):
    """Download to `dest`, resuming a partial file with a Range request after a dropped connection."""
    last = None
    for attempt in range(tries):
        have = os.path.getsize(dest) if os.path.exists(dest) else 0
        if expect_bytes and have == expect_bytes:
            return dest
        if expect_bytes and have > expect_bytes:
            os.remove(dest)
            have = 0
        try:
            req = _request(url, {"Range": "bytes=%d-" % have} if have else None)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if have and resp.status != 206:  # the server ignored the range: start again
                    have = 0
                with open(dest, "ab" if have else "wb") as out:
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
            size = os.path.getsize(dest)
            if expect_bytes and size != expect_bytes:
                raise SourceError("got %d of %d bytes" % (size, expect_bytes))
            return dest
        except Exception as exc:
            last = exc
            log("download attempt %d failed: %s" % (attempt + 1, exc))
            if attempt + 1 < tries:
                time.sleep(pause * (attempt + 1))
    raise SourceError("could not download %s (%s)" % (url, last))


# ---------------------------------------------------------------------------------------------- USDA NASS

def find_nass_economics(html, base=NASS_LISTING):
    """URL and file date of the newest qs.economics_YYYYMMDD.txt.gz linked from the NASS datasets page."""
    found = re.findall(r'href="([^"]*qs\.economics_(\d{8})\.txt\.gz)"', html)
    if not found:
        raise SourceError("no qs.economics_*.txt.gz link on %s" % base)
    href, stamp = max(found, key=lambda m: m[1])
    return urllib.parse.urljoin(base, href), "%s-%s-%s" % (stamp[:4], stamp[4:6], stamp[6:])


def _num(text):
    """'12,345' -> '12345'; suppressed or unpublished markers such as '(D)' -> ''."""
    t = text.strip().replace(",", "")
    if not t or t.startswith("("):
        return ""
    try:
        float(t)
    except ValueError:
        return ""
    return t


def parse_nass(lines):
    """Read Quick Stats rows (an iterable of tab-separated text lines, header first) into the USDA tables.

    Returns {file name: list of row dicts}. Rows are keyed so that a later LOAD_TIME replaces an earlier one.
    """
    it = iter(lines)
    cols = [c.strip() for c in next(it).replace("\x00", "").split("\t")]
    need = ["SOURCE_DESC", "COMMODITY_DESC", "SHORT_DESC", "DOMAIN_DESC", "AGG_LEVEL_DESC", "STATE_FIPS_CODE",
            "STATE_ALPHA", "COUNTY_ANSI", "COUNTY_CODE", "COUNTY_NAME", "YEAR", "FREQ_DESC", "REFERENCE_PERIOD_DESC",
            "LOAD_TIME", "VALUE", "CV_%"]
    missing = [c for c in need if c not in cols]
    if missing:
        raise SourceError("Quick Stats columns missing: %s" % ", ".join(missing))
    ix = {c: cols.index(c) for c in need}
    i_com, i_short, i_src, i_dom, i_agg = (ix[k] for k in ("COMMODITY_DESC", "SHORT_DESC", "SOURCE_DESC",
                                                         "DOMAIN_DESC", "AGG_LEVEL_DESC"))
    width = max(ix.values())

    county, census_state, survey, rent_c, rent_s = {}, {}, {}, {}, {}
    loads = {}

    def put(table, key, col, value, load, extra=None):
        mark = (id(table), key, col)
        if mark in loads and loads[mark] > load:
            return
        loads[mark] = load
        row = table.setdefault(key, {})
        row[col] = value
        if extra:
            row.update(extra)

    for line in it:
        if "\x00" in line:
            line = line.replace("\x00", "")
        p = line.split("\t")
        if len(p) <= width or p[i_com] not in WANTED_COMMODITIES or p[i_dom] != "TOTAL":
            continue
        short, src, agg = p[i_short], p[i_src], p[i_agg]
        year = p[ix["YEAR"]].strip()
        state = p[ix["STATE_ALPHA"]].strip()
        load = p[ix["LOAD_TIME"]].strip()
        raw = p[ix["VALUE"]].strip()
        value = _num(raw)
        if not year.isdigit():
            continue
        if src == "CENSUS" and short in CENSUS_COLS:
            col = CENSUS_COLS[short]
            if agg == "COUNTY":
                sf = p[ix["STATE_FIPS_CODE"]].strip().zfill(2)
                code = (p[ix["COUNTY_ANSI"]].strip() or p[ix["COUNTY_CODE"]].strip()).zfill(3)
                if not sf.isdigit() or not code.isdigit() or code in ("998", "999"):
                    continue
                extra = {"state": state, "county_name": p[ix["COUNTY_NAME"]].strip()}
                if short == LAND_VALUE:
                    extra["cv_pct"] = _num(p[ix["CV_%"]])
                    extra["suppressed"] = "1" if raw == "(D)" else ""
                put(county, (sf + code, year), col, value, load, extra)
            elif agg in ("STATE", "NATIONAL"):
                put(census_state, ("US" if agg == "NATIONAL" else state, year), col, value, load)
        elif src == "SURVEY" and p[ix["FREQ_DESC"]].strip() == "ANNUAL" and p[ix["REFERENCE_PERIOD_DESC"]].strip() == "YEAR":
            if short in SURVEY_VALUE_COLS and agg in ("STATE", "NATIONAL"):
                if agg == "STATE" and (len(state) != 2 or state == "OT"):
                    continue
                put(survey, ("US" if agg == "NATIONAL" else state, year), SURVEY_VALUE_COLS[short], value, load)
            elif short in RENT_COLS:
                if agg == "COUNTY" and short != RENT_CROPLAND:
                    sf = p[ix["STATE_FIPS_CODE"]].strip().zfill(2)
                    code = p[ix["COUNTY_ANSI"]].strip()
                    if not code.isdigit() or not sf.isdigit():  # "other (combined) counties" have no county code
                        continue
                    put(rent_c, (sf + code.zfill(3), year), RENT_COLS[short], value, load,
                        {"state": state, "county_name": p[ix["COUNTY_NAME"]].strip()})
                elif agg in ("STATE", "NATIONAL"):
                    if agg == "STATE" and (len(state) != 2 or state == "OT"):
                        continue
                    put(rent_s, ("US" if agg == "NATIONAL" else state, year), RENT_COLS[short], value, load)

    def rows(table, key_names, keep=None):
        out = []
        for key in sorted(table):
            row = dict(zip(key_names, key))
            row.update(table[key])
            if keep is None or keep(row):
                out.append(row)
        return out

    return {
        "usda_county_land_value.csv": rows(county, ("fips", "year"), lambda r: "value_per_acre" in r),
        "usda_census_state_land_value.csv": rows(census_state, ("state", "year"), lambda r: r.get("value_per_acre")),
        "usda_state_land_value.csv": rows(survey, ("state", "year"),
                                          lambda r: any(r.get(c) for c in SURVEY_VALUE_COLS.values())),
        "usda_county_cash_rent.csv": rows(rent_c, ("fips", "year"),
                                          lambda r: any(r.get(c) for c in RENT_COLS.values())),
        "usda_state_cash_rent.csv": rows(rent_s, ("state", "year"),
                                         lambda r: any(r.get(c) for c in RENT_COLS.values())),
    }


def parse_nass_file(path):
    with gzip.open(path, "rt", encoding="latin-1", newline="") as fh:
        return parse_nass(fh)


def validate_nass(tables):
    """Refuse an extract that cannot be a complete Quick Stats economics file."""
    county = tables["usda_county_land_value.csv"]
    survey = tables["usda_state_land_value.csv"]
    years = sorted({r["year"] for r in county})
    problems = []
    if len(years) < 5:
        problems.append("county land values cover only %d census years" % len(years))
    latest = [r for r in county if years and r["year"] == years[-1] and r.get("value_per_acre")]
    if len(latest) < 2800:
        problems.append("only %d counties have a value in the latest census" % len(latest))
    states = {r["state"] for r in survey if r["state"] != "US" and r.get("farm_real_estate")}
    if len(states) < 45:
        problems.append("the state survey covers only %d states" % len(states))
    if not any(r["state"] == "US" and r.get("farm_real_estate") for r in survey):
        problems.append("no national survey value")
    for r in latest:
        v = float(r["value_per_acre"])
        if not 20 <= v <= 5000000:
            problems.append("implausible value %s for %s %s" % (r["value_per_acre"], r["fips"], r["year"]))
            break
    if problems:
        raise SourceError("USDA extract failed validation: " + "; ".join(problems))
    return tables


# ---------------------------------------------------------------------------------------------- FHFA

def find_fhfa_workbook(html, base=FHFA_PAGE):
    """The newest land price workbook attached to the working paper page.

    Attachments carry their date in the file name ("land-prices_2024_20_june.xlsx"). The newest year wins; the
    page lists newest first, which breaks ties.
    """
    hrefs = re.findall(r'href="([^"]+\.xlsx)(?:\?[^"]*)?"', html, flags=re.I)
    picks = []
    for pos, href in enumerate(hrefs):
        name = href.rsplit("/", 1)[-1].lower()
        if "land" in name and "price" in name:
            yrs = [int(y) for y in re.findall(r"(?<!\d)(20\d\d)(?!\d)", name)]
            picks.append((max(yrs) if yrs else 0, -pos, href))
    if not picks:
        raise SourceError("no land price workbook linked from %s" % base)
    return urllib.parse.urljoin(base, max(picks)[2])


FHFA_COLUMNS = [  # (substring of the normalised header, output column); the first match wins
    ("1/4 acre", "land_value_quarter_acre_std"),
    ("per acre", "land_value_per_acre"),
    ("land share", "land_share"),
    ("property value (standardized)", "property_value_std"),
    ("property value (as-is)", "property_value"),
    ("lot size", "lot_size_sqft"),
    ("interior square", "interior_sqft"),
    ("state abbreviation", "state"),
    ("state fips", "state_fips"),
    ("state name", "state_name"),
    ("fips", "fips"),
    ("county", "county_name"),
    ("state", "state_name"),
    ("year", "year"),
]


def _fhfa_sheet(book, name, key):
    part = book.find(name)
    if part is None:
        raise SourceError("FHFA workbook has no sheet named %r" % name)
    header, out = None, []
    for row in book.rows(part):
        cells = [(" ".join(str(c).lower().split()) if c is not None else "") for c in row]
        if header is None:
            if any(c == key for c in cells):
                header = []
                for c in cells:
                    header.append(next((col for sub, col in FHFA_COLUMNS if c and sub in c), None))
            continue
        rec = {}
        for col, val in zip(header, row):
            if col and val is not None and str(val).strip() != "":
                rec.setdefault(col, str(val).strip())
        if rec:
            out.append(rec)
    if header is None:
        raise SourceError("FHFA sheet %r has no header row with a %r column" % (name, key))
    return out


def _fnum(text, digits=0):
    """Tidy a spreadsheet number: '0.19500000000000001' -> '0.195', '52900.0' -> '52900'."""
    if text is None or str(text).strip() == "":
        return ""
    try:
        v = float(text)
    except ValueError:
        return ""
    if digits:
        return ("%.*f" % (digits, v)).rstrip("0").rstrip(".")
    return str(int(round(v)))


def _fhfa_values(rec):
    return {"land_value_per_acre": _fnum(rec.get("land_value_per_acre")),
            "land_value_quarter_acre_std": _fnum(rec.get("land_value_quarter_acre_std")),
            "land_share": _fnum(rec.get("land_share"), 4),
            "property_value": _fnum(rec.get("property_value")),
            "property_value_std": _fnum(rec.get("property_value_std"))}


def _fips5(text):
    t = _fnum(text)
    return t.zfill(5) if t else ""


def parse_fhfa(path):
    """Read the county, state and national sheets of the FHFA land price workbook."""
    try:
        book = Workbook(path)
    except Exception as exc:
        raise SourceError("FHFA workbook is not a readable .xlsx (%s)" % exc)
    try:
        version = ""
        readme = book.find("Readme")
        if readme:
            for row in book.rows(readme):
                for c in row:
                    if c and str(c).strip().lower().startswith("version"):
                        version = str(c).strip()
                        break
                if version:
                    break
        county_panel, county_cs, state_panel, nation = [], [], [], []
        for rec in _fhfa_sheet(book, "Panel Counties", "fips"):
            fips, year = _fips5(rec.get("fips")), _fnum(rec.get("year"))
            if fips and year:
                county_panel.append(dict(_fhfa_values(rec), fips=fips, year=year))
        for rec in _fhfa_sheet(book, "Cross-Section Counties", "fips"):
            fips = _fips5(rec.get("fips"))
            if fips:
                county_cs.append(dict(_fhfa_values(rec), fips=fips, state_name=rec.get("state_name", ""),
                                      county_name=rec.get("county_name", ""),
                                      lot_size_sqft=_fnum(rec.get("lot_size_sqft")),
                                      interior_sqft=_fnum(rec.get("interior_sqft"))))
        for rec in _fhfa_sheet(book, "Panel States", "year"):
            state, year = (rec.get("state") or "").upper(), _fnum(rec.get("year"))
            if len(state) == 2 and year:
                state_panel.append(dict(_fhfa_values(rec), state=state, year=year))
        for rec in _fhfa_sheet(book, "Panel Nation", "year"):
            year = _fnum(rec.get("year"))
            if year:
                nation.append(dict(_fhfa_values(rec), year=year))
    finally:
        book.close()
    county_panel.sort(key=lambda r: (r["fips"], r["year"]))
    county_cs.sort(key=lambda r: r["fips"])
    state_panel.sort(key=lambda r: (r["state"], r["year"]))
    nation.sort(key=lambda r: r["year"])
    return {"fhfa_county_panel.csv": county_panel, "fhfa_county_cross_section.csv": county_cs,
            "fhfa_state_panel.csv": state_panel, "fhfa_nation_panel.csv": nation}, version


def validate_fhfa(tables):
    panel, cs = tables["fhfa_county_panel.csv"], tables["fhfa_county_cross_section.csv"]
    problems = []
    if len({r["fips"] for r in panel}) < 500:
        problems.append("county panel covers only %d counties" % len({r["fips"] for r in panel}))
    if len(cs) < 1500:
        problems.append("county cross-section has only %d counties" % len(cs))
    if len({r["year"] for r in panel}) < 8:
        problems.append("county panel has only %d years" % len({r["year"] for r in panel}))
    if not tables["fhfa_nation_panel.csv"]:
        problems.append("no national panel")
    priced = [r for r in panel if r["land_value_per_acre"]]
    if len(priced) < 0.9 * len(panel):
        problems.append("most county panel rows have no land value")
    for r in priced:
        if not 100 <= float(r["land_value_per_acre"]) <= 500000000:
            problems.append("implausible land value %s for %s" % (r["land_value_per_acre"], r["fips"]))
            break
    if problems:
        raise SourceError("FHFA extract failed validation: " + "; ".join(problems))
    return tables


# ---------------------------------------------------------------------------------------------- data/ files

def csv_text(name, rows):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=FILES[name], extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in FILES[name]})
    return out.getvalue()


def read_csv(name, data_dir=None):
    path = os.path.join(data_dir or config.DATA, name)
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_status(data_dir=None):
    path = os.path.join(data_dir or config.DATA, "status.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {"sources": {}}


def save_status(status, data_dir=None):
    path = os.path.join(data_dir or config.DATA, "status.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(status, fh, indent=1, sort_keys=True)
        fh.write("\n")


# ---------------------------------------------------------------------------------------------- check

def check():
    """Print what each source offers right now. Exit 1 when a source cannot be reached."""
    bad = 0
    try:
        url, stamp = find_nass_economics(fetch_text(NASS_LISTING))
        info = head(url)
        print("USDA NASS  ok   %s  file date %s  %.0f MB  last-modified %s" % (url, stamp, info["bytes"] / 1e6,
                                                                              info["last_modified"]))
    except SourceError as exc:
        bad += 1
        print("USDA NASS  FAIL %s" % exc)
    try:
        url = find_fhfa_workbook(fetch_text(FHFA_PAGE))
        info = head(url)
        print("FHFA       ok   %s  %.1f MB  last-modified %s" % (url, info["bytes"] / 1e6, info["last_modified"]))
    except SourceError as exc:
        bad += 1
        print("FHFA       FAIL %s" % exc)
    return 1 if bad else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["check"]:
        sys.exit(check())
    print(__doc__)
    sys.exit(2)
