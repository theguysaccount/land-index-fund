"""Synthetic inputs: a few Quick Stats lines, a tiny FHFA workbook and two square counties.

Nothing here copies launch-day numbers from the real data, so the tests keep passing when the sources update.
"""
import gzip
import json
import os
import zipfile

from landindex import sources

COLS = ["SOURCE_DESC", "SECTOR_DESC", "GROUP_DESC", "COMMODITY_DESC", "CLASS_DESC", "PRODN_PRACTICE_DESC",
        "UTIL_PRACTICE_DESC", "STATISTICCAT_DESC", "UNIT_DESC", "SHORT_DESC", "DOMAIN_DESC", "DOMAINCAT_DESC",
        "AGG_LEVEL_DESC", "STATE_ANSI", "STATE_FIPS_CODE", "STATE_ALPHA", "STATE_NAME", "ASD_CODE", "ASD_DESC",
        "COUNTY_ANSI", "COUNTY_CODE", "COUNTY_NAME", "REGION_DESC", "ZIP_5", "WATERSHED_CODE", "WATERSHED_DESC",
        "CONGR_DISTRICT_CODE", "COUNTRY_CODE", "COUNTRY_NAME", "LOCATION_DESC", "YEAR", "FREQ_DESC", "BEGIN_CODE",
        "END_CODE", "REFERENCE_PERIOD_DESC", "WEEK_ENDING", "LOAD_TIME", "VALUE", "CV_%"]

LOAD = "2024-07-02 12:00:00"
IA_SURVEY = {2017: 7300, 2018: 7260, 2019: 7340, 2020: 7480, 2021: 8380, 2022: 9600, 2023: 9750, 2024: 9800,
             2025: 9900, 2026: 10200}
US_SURVEY = {1997: 900, 2017: 3080, 2022: 3700, 2025: 4300, 2026: 4450}


def line(source, short, agg, year, value, state="IA", state_fips="19", county_ansi="", county_name="", cv="",
         commodity=None, freq=None, ref=None, load=LOAD, domain="TOTAL"):
    commodity = commodity or short.split(",")[0].split(" - ")[0]
    if freq is None:
        freq = "POINT IN TIME" if source == "CENSUS" else "ANNUAL"
    if ref is None:
        ref = "END OF DEC" if source == "CENSUS" else "YEAR"
    row = dict.fromkeys(COLS, "")
    row.update({"SOURCE_DESC": source, "COMMODITY_DESC": commodity, "SHORT_DESC": short, "DOMAIN_DESC": domain,
                "AGG_LEVEL_DESC": agg, "STATE_FIPS_CODE": state_fips if agg != "NATIONAL" else "99",
                "STATE_ALPHA": state if agg != "NATIONAL" else "US", "COUNTY_ANSI": county_ansi,
                "COUNTY_CODE": county_ansi or ("998" if county_name else ""), "COUNTY_NAME": county_name,
                "YEAR": str(year), "FREQ_DESC": freq, "REFERENCE_PERIOD_DESC": ref, "LOAD_TIME": load,
                "VALUE": value, "CV_%": cv})
    return "\t".join(row[c] for c in COLS) + "\r\n"


def nass_lines():
    out = ["\t".join(COLS) + "\r\n"]
    V = sources.LAND_VALUE
    # Story County: census observations, acres and farms
    for y, v, cv in ((2017, "9,467", "4.1"), (2022, "10,914", "5.0")):
        out.append(line("CENSUS", V, "COUNTY", y, v, county_ansi="169", county_name="STORY", cv=cv))
    out.append(line("CENSUS", sources.ACRES, "COUNTY", 2022, "335,000", county_ansi="169", county_name="STORY",
                    commodity="FARM OPERATIONS"))
    out.append(line("CENSUS", sources.FARMS, "COUNTY", 2022, "780", county_ansi="169", county_name="STORY",
                    commodity="FARM OPERATIONS"))
    # Adair County: withheld in 2017, published in 2022; an older load of 2022 must lose to the newer one
    out.append(line("CENSUS", V, "COUNTY", 2017, "(D)", county_ansi="001", county_name="ADAIR"))
    out.append(line("CENSUS", V, "COUNTY", 2022, "4,000", county_ansi="001", county_name="ADAIR", load="2023-01-01 00:00:00"))
    out.append(line("CENSUS", V, "COUNTY", 2022, "5,000", county_ansi="001", county_name="ADAIR", load="2025-01-01 00:00:00"))
    # a non-total domain row that must be ignored
    out.append(line("CENSUS", V, "COUNTY", 2022, "99", county_ansi="169", county_name="STORY", domain="AREA OPERATED"))
    # state and national census values
    out.append(line("CENSUS", V, "STATE", 2017, "7,700"))
    out.append(line("CENSUS", V, "STATE", 2022, "9,253"))
    out.append(line("CENSUS", V, "NATIONAL", 2017, "2,976"))
    out.append(line("CENSUS", V, "NATIONAL", 2022, "3,846"))
    # annual survey
    for y, v in IA_SURVEY.items():
        out.append(line("SURVEY", V, "STATE", y, "{:,}".format(v)))
    for y in (2025, 2026):
        out.append(line("SURVEY", sources.CROPLAND_VALUE, "STATE", y, "{:,}".format(IA_SURVEY[y] + 400)))
        out.append(line("SURVEY", sources.PASTURE_VALUE, "STATE", y, "3,700"))
    for y, v in US_SURVEY.items():
        out.append(line("SURVEY", V, "NATIONAL", y, "{:,}".format(v)))
    # "other states" aggregate must be skipped
    out.append(line("SURVEY", V, "STATE", 2026, "1,000", state="OT", state_fips="98"))
    # county cash rents, including an "other (combined) counties" row without a county code
    for y, v in ((2025, "278"), (2026, "290")):
        out.append(line("SURVEY", sources.RENT_NONIRR, "COUNTY", y, v, county_ansi="169", county_name="STORY", commodity="RENT"))
    out.append(line("SURVEY", sources.RENT_PASTURE, "COUNTY", 2026, "63.5", county_ansi="169", county_name="STORY", commodity="RENT"))
    out.append(line("SURVEY", sources.RENT_NONIRR, "COUNTY", 2026, "250", county_name="OTHER (COMBINED) COUNTIES", commodity="RENT"))
    out.append(line("SURVEY", sources.RENT_CROPLAND, "STATE", 2026, "270", commodity="RENT"))
    # a line with NUL bytes, as the real file has
    out.append(line("SURVEY", sources.RENT_PASTURE, "STATE", 2026, "60", commodity="RENT").replace("RENT", "RE\x00NT", 1)
               .replace("\x00", "", 0))
    return out


def write_nass_gz(path):
    with gzip.open(path, "wt", encoding="latin-1", newline="") as fh:
        fh.writelines(nass_lines())


def _cell(ref, value):
    if isinstance(value, (int, float)):
        return '<c r="%s"><v>%s</v></c>' % (ref, value)
    return '<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (ref, value)


def _sheet(rows):
    xml = []
    for i, row in enumerate(rows, 1):
        cells = "".join(_cell("%s%d" % (chr(65 + j), i), v) for j, v in enumerate(row) if v is not None)
        xml.append('<row r="%d">%s</row>' % (i, cells))
    return ('<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>%s</sheetData></worksheet>" % "".join(xml))


def write_fhfa_xlsx(path, counties=(("Iowa", "Story County", 19169),), years=range(2012, 2023)):
    head = ["Land Value\n(1/4 Acre Lot, Standardized)", "Land Value\n(Per Acre, As-Is)", "Land Share of Property Value",
            "Property Value (Standardized)", "Property Value (As-is)"]
    sheets = {
        "Readme": [[None, "The Price of Residential Land"], [None, "Version 9.9 (Test, 2099)"]],
        "Panel Counties": [[None, None, None, None, "All Single-Family Parcels"], ["State", "County", "FIPS", "Year"] + head]
        + [[s, c, f, y, 60000 + y, 200000 + 10 * y, 0.29900000000000002, 214000, 210000] for s, c, f in counties for y in years],
        "Cross-Section Counties ": [[None, None, None, "All Single-Family Parcels"],
                                    ["State", "County", "FIPS"] + head[:3] + ["Lot Size", "Interior Square Feet"] + head[3:]]
        + [[s, c, f, 41800, 136700, 0.255, 13770, 1700, 169600, 170000] for s, c, f in counties],
        "Panel States": [[None, None, None, None, "All"], ["State Name", "State Abbreviation", "State FIPS", "Year"] + head]
        + [["Iowa", "IA", 19, y, 30000, 90000, 0.2, 150000, 150000] for y in years],
        "Panel Nation": [[None, "All"], ["Year"] + head] + [[y, 100000, 400000 + y, 0.37, 260000, 250000] for y in years],
    }
    names = list(sheets)
    wb = ('<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>%s</sheets></workbook>' % "".join(
              '<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (n, i + 1, i + 1) for i, n in enumerate(names)))
    rels = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">%s'
            "</Relationships>" % "".join(
                '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                'Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1) for i in range(len(names))))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        for i, n in enumerate(names):
            z.writestr("xl/worksheets/sheet%d.xml" % (i + 1), _sheet(sheets[n]))


def square(x, y, size=200):
    return [x, y, size, 0, 0, size, -size, 0, 0, -size]


def write_geo(data_dir):
    os.makedirs(os.path.join(data_dir, "geo"), exist_ok=True)
    counties = [
        {"f": "19169", "n": "Story County", "s": "IA", "sn": "Iowa", "a": 573, "c": [5100, 2100], "p": [square(5000, 2000)], "nb": ["19001"]},
        {"f": "19001", "n": "Adair County", "s": "IA", "sn": "Iowa", "a": 570, "c": [5300, 2100], "p": [square(5200, 2000)], "nb": ["19169"]},
    ]
    states = [{"f": "19", "s": "IA", "n": "Iowa", "p": [square(5000, 2000, 400)]}]
    meta = {"source": "test", "width": 975, "height": 610, "scale": 10}
    with open(os.path.join(data_dir, "geo", "counties.json"), "w") as fh:
        json.dump({"meta": meta, "counties": counties}, fh)
    with open(os.path.join(data_dir, "geo", "states.json"), "w") as fh:
        json.dump({"meta": meta, "states": states}, fh)


def make_data_dir(data_dir, work):
    """A complete data/ folder built through the real parsers from the synthetic inputs."""
    os.makedirs(data_dir, exist_ok=True)
    nass = os.path.join(work, "qs.txt.gz")
    fhfa = os.path.join(work, "fhfa.xlsx")
    write_nass_gz(nass)
    write_fhfa_xlsx(fhfa)
    tables = sources.parse_nass_file(nass)
    ftables, version = sources.parse_fhfa(fhfa)
    tables.update(ftables)
    for name in sources.FILES:
        with open(os.path.join(data_dir, name), "w", encoding="utf-8", newline="") as fh:
            fh.write(sources.csv_text(name, tables[name]))
    sources.save_status({"checked": "2099-01-02", "sources": {
        "usda": {"label": "USDA NASS Quick Stats", "ok": True, "changed": "2099-01-01", "checked": "2099-01-02", "failures": 0},
        "fhfa": {"label": "FHFA residential land prices", "ok": True, "changed": "2099-01-01", "checked": "2099-01-02",
                 "failures": 0, "version": version}}}, data_dir)
    write_geo(data_dir)
    return data_dir
