import os
import shutil
import tempfile
import unittest

from landindex import sources
from landindex.sources import SourceError
from tests import fixtures


class NassTest(unittest.TestCase):
    def setUp(self):
        self.t = sources.parse_nass(fixtures.nass_lines())

    def row(self, name, **kw):
        rows = [r for r in self.t[name] if all(r.get(k) == v for k, v in kw.items())]
        self.assertEqual(len(rows), 1, (name, kw, rows))
        return rows[0]

    def test_county_census_values_acres_and_cv(self):
        r = self.row("usda_county_land_value.csv", fips="19169", year="2022")
        self.assertEqual((r["value_per_acre"], r["cv_pct"], r["acres_in_farms"], r["farms"]), ("10914", "5.0", "335000", "780"))
        self.assertEqual((r["state"], r["county_name"]), ("IA", "STORY"))

    def test_withheld_values_are_kept_as_suppressed(self):
        r = self.row("usda_county_land_value.csv", fips="19001", year="2017")
        self.assertEqual((r["value_per_acre"], r["suppressed"]), ("", "1"))

    def test_newer_load_time_wins(self):
        self.assertEqual(self.row("usda_county_land_value.csv", fips="19001", year="2022")["value_per_acre"], "5000")

    def test_non_total_domains_are_ignored(self):
        self.assertNotEqual(self.row("usda_county_land_value.csv", fips="19169", year="2022")["value_per_acre"], "99")

    def test_survey_state_and_national(self):
        self.assertEqual(self.row("usda_state_land_value.csv", state="IA", year="2026")["farm_real_estate"],
                         str(fixtures.IA_SURVEY[2026]))
        self.assertEqual(self.row("usda_state_land_value.csv", state="US", year="2026")["farm_real_estate"],
                         str(fixtures.US_SURVEY[2026]))
        self.assertFalse([r for r in self.t["usda_state_land_value.csv"] if r["state"] == "OT"])

    def test_census_state_and_national(self):
        self.assertEqual(self.row("usda_census_state_land_value.csv", state="US", year="2022")["value_per_acre"], "3846")

    def test_cash_rents_skip_combined_counties_and_survive_nul_bytes(self):
        rent = self.t["usda_county_cash_rent.csv"]
        self.assertEqual({r["fips"] for r in rent}, {"19169"})
        r = self.row("usda_county_cash_rent.csv", fips="19169", year="2026")
        self.assertEqual((r["cropland_nonirrigated"], r["pasture"]), ("290", "63.5"))
        self.assertEqual(self.row("usda_state_cash_rent.csv", state="IA", year="2026")["pasture"], "60")

    def test_missing_columns_are_an_error(self):
        with self.assertRaises(SourceError):
            sources.parse_nass(["A\tB\n", "1\t2\n"])

    def test_validation_refuses_a_partial_file(self):
        with self.assertRaises(SourceError):
            sources.validate_nass(self.t)

    def test_number_cleaning(self):
        self.assertEqual(sources._num("12,345"), "12345")
        self.assertEqual(sources._num("(D)"), "")
        self.assertEqual(sources._num("(Z)"), "")
        self.assertEqual(sources._num(""), "")


class ListingTest(unittest.TestCase):
    def test_newest_nass_file_wins(self):
        html = ('<a href="/sites/default/files/datasets/qs.economics_20260101.txt.gz">a</a>'
                '<a href="/sites/default/files/datasets/qs.economics_20261106.txt.gz">b</a>'
                '<a href="/sites/default/files/datasets/qs.crops_20261201.txt.gz">c</a>')
        url, stamp = sources.find_nass_economics(html)
        self.assertTrue(url.endswith("qs.economics_20261106.txt.gz"))
        self.assertTrue(url.startswith("https://www.nass.usda.gov/"))
        self.assertEqual(stamp, "2026-11-06")
        with self.assertRaises(SourceError):
            sources.find_nass_economics("<html></html>")

    def test_newest_fhfa_workbook_wins(self):
        html = ('<a href="/document/land-prices_2024_20_june.xlsx">2024</a>'
                '<a href="/sites/default/files/Land-Prices_DLOS_2020_26Oct.xlsx">2020</a>'
                '<a href="/document/other-data_2030.xlsx">other</a>')
        self.assertTrue(sources.find_fhfa_workbook(html).endswith("/document/land-prices_2024_20_june.xlsx"))
        html2 = html + '<a href="/document/Land-Prices_2027_03_march.xlsx">new</a>'
        self.assertTrue(sources.find_fhfa_workbook(html2).endswith("Land-Prices_2027_03_march.xlsx"))
        with self.assertRaises(SourceError):
            sources.find_fhfa_workbook("<a href='x.pdf'>")


class FhfaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "fhfa.xlsx")
        fixtures.write_fhfa_xlsx(self.path)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_sheets_parse(self):
        t, version = sources.parse_fhfa(self.path)
        self.assertIn("Version", version)
        panel = t["fhfa_county_panel.csv"]
        self.assertEqual({r["fips"] for r in panel}, {"19169"})
        r = [x for x in panel if x["year"] == "2022"][0]
        self.assertEqual((r["land_value_per_acre"], r["land_share"]), (str(200000 + 20220), "0.299"))
        cs = t["fhfa_county_cross_section.csv"][0]
        self.assertEqual((cs["fips"], cs["lot_size_sqft"], cs["county_name"]), ("19169", "13770", "Story County"))
        self.assertEqual(t["fhfa_state_panel.csv"][0]["state"], "IA")
        self.assertEqual(len(t["fhfa_nation_panel.csv"]), 11)

    def test_validation_refuses_a_tiny_workbook(self):
        t, _ = sources.parse_fhfa(self.path)
        with self.assertRaises(SourceError):
            sources.validate_fhfa(t)

    def test_a_broken_file_is_a_source_error(self):
        bad = os.path.join(self.tmp, "bad.xlsx")
        with open(bad, "w") as fh:
            fh.write("not a zip")
        with self.assertRaises(SourceError):
            sources.parse_fhfa(bad)


class CsvTest(unittest.TestCase):
    def test_round_trip_keeps_column_order(self):
        text = sources.csv_text("usda_state_land_value.csv", [{"state": "IA", "year": "2026", "farm_real_estate": "1"}])
        self.assertEqual(text.splitlines()[0], ",".join(sources.FILES["usda_state_land_value.csv"]))
        self.assertEqual(text.splitlines()[1], "IA,2026,1,,")


if __name__ == "__main__":
    unittest.main()
