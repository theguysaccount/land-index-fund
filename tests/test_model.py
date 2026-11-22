import csv
import os
import shutil
import tempfile
import unittest

from landindex import config, model
from landindex.model import Index, county_series, sig
from tests import fixtures


class SeriesTest(unittest.TestCase):
    STATE = {2017: 100.0, 2018: 110.0, 2019: 120.0, 2020: 130.0, 2021: 140.0, 2022: 150.0, 2023: 165.0, 2024: 180.0}

    def test_census_years_are_exact_and_estimates_follow_the_state(self):
        s = county_series({2017: 1000.0, 2022: 2000.0}, self.STATE, 2024)
        by = {y: (v, k) for y, v, k in s}
        self.assertEqual(by[2017], (1000.0, "census"))
        self.assertEqual(by[2022], (2000.0, "census"))
        self.assertEqual([k for _, _, k in s].count("interpolated"), 4)
        self.assertEqual(by[2024], (sig(2000.0 * 180 / 150), "estimate"))
        self.assertEqual(by[2023], (sig(2000.0 * 165 / 150), "estimate"))

    def test_interpolation_bridges_the_county_gap_smoothly(self):
        s = {y: v for y, v, _ in county_series({2017: 1000.0, 2022: 3000.0}, self.STATE, 2022)}
        # the county tripled while its state grew 50%: every year between must sit between the two censuses
        self.assertTrue(all(1000 < s[y] < 3000 for y in range(2018, 2022)))
        self.assertTrue(all(s[y] < s[y + 1] for y in range(2017, 2022)))

    def test_no_state_survey_means_census_points_only(self):
        s = county_series({2017: 1000.0, 2022: 2000.0}, {}, 2026)
        self.assertEqual([k for _, _, k in s], ["census", "census"])

    def test_no_observation_no_series(self):
        self.assertEqual(county_series({}, self.STATE, 2024), [])

    def test_significant_figures(self):
        self.assertEqual(sig(12345.0), 12300)
        self.assertEqual(sig(987.6), 988)
        self.assertEqual(sig(0), 0)

    def test_slugs(self):
        self.assertEqual(model.slugify("St. Mary's Parish"), "st-marys-parish")
        self.assertEqual(model.slugify("Doña Ana County"), "dona-ana-county")


class IndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.data = fixtures.make_data_dir(os.path.join(cls.tmp, "data"), cls.tmp)
        cls.ix = Index(cls.data)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_years_come_from_the_data(self):
        self.assertEqual(self.ix.census_year, 2022)
        self.assertEqual(self.ix.survey_year, max(fixtures.US_SURVEY))

    def test_story_county(self):
        c = self.ix.counties["19169"]
        self.assertEqual(c["label"], "Story County, Iowa")
        self.assertEqual(self.ix.county_path(c), "/iowa/story-county/")
        self.assertEqual(c["latest_obs"], (2022, 10914.0))
        est_year, est_value, base = c["estimate"]
        self.assertEqual((est_year, base), (2026, 2022))
        self.assertEqual(est_value, sig(10914.0 * fixtures.IA_SURVEY[2026] / fixtures.IA_SURVEY[2022]))
        self.assertEqual(c["rank_state"], 1)
        self.assertEqual(c["neighbors"], ["19001"])
        self.assertIn(2026, c["rent"])

    def test_withheld_county_still_ranks_on_its_latest_value(self):
        c = self.ix.counties["19001"]
        self.assertTrue(c["census"][2017]["suppressed"])
        self.assertEqual(c["obs"], {2022: 5000.0})
        self.assertEqual(c["rank_state"], 2)

    def test_public_json_carries_the_notice(self):
        j = self.ix.county_json(self.ix.counties["19169"])
        self.assertTrue(j["notes"]["not_investment_advice"])
        self.assertTrue(j["url"].startswith(config.BASE_URL))


class RealDataTest(unittest.TestCase):
    """Invariants of the committed data that hold whatever the sources publish next."""

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(os.path.join(config.DATA, "usda_county_land_value.csv")):
            raise unittest.SkipTest("no committed data")
        cls.ix = Index()

    def test_every_census_point_equals_the_usda_figure(self):
        with open(os.path.join(config.DATA, "usda_county_land_value.csv")) as fh:
            src = {(r["fips"], int(r["year"])): r["value_per_acre"] for r in csv.DictReader(fh)}
        n = 0
        for c in self.ix.counties.values():
            for y, v, k in c["series"]:
                if k == "census":
                    self.assertEqual(float(src[(c["fips"], y)]), v)
                    n += 1
        self.assertGreater(n, 0)

    def test_every_estimate_is_the_census_value_moved_by_the_state(self):
        for c in self.ix.counties.values():
            est = c.get("estimate")
            if not est:
                continue
            st = self.ix.states[c["state"]]["series"]
            self.assertEqual(est[1], sig(c["obs"][est[2]] * st[est[0]] / st[est[2]]), c["label"])

    def test_paths_are_unique(self):
        paths = [self.ix.county_path(c) for c in self.ix.counties.values()]
        self.assertEqual(len(paths), len(set(paths)))


if __name__ == "__main__":
    unittest.main()
