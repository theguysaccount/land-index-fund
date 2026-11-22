import io
import json
import os
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

from landindex import build, config
from tests import fixtures

import importlib.util

_spec = importlib.util.spec_from_file_location("check_dist", os.path.join(config.ROOT, "scripts", "check_dist.py"))
check_dist = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_dist)


class BuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.data = fixtures.make_data_dir(os.path.join(cls.tmp, "data"), cls.tmp)
        cls.dist = os.path.join(cls.tmp, "dist")
        build.build(cls.dist, cls.data, log=lambda *a: None)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def read(self, rel):
        with open(os.path.join(self.dist, rel), encoding="utf-8") as fh:
            return fh.read()

    def test_the_guard_passes_on_a_fresh_build(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = check_dist.main(self.dist, self.data)
        self.assertEqual(code, 0, out.getvalue())

    def test_core_pages_exist(self):
        for rel in ("index.html", "states/index.html", "rankings/index.html", "methodology/index.html", "data/index.html",
                    "about/index.html", "iowa/index.html", "iowa/story-county/index.html", "iowa/adair-county/index.html",
                    "embed/index.html", "404.html", "sitemap.xml", "robots.txt", "assets/us-counties.svg",
                    "api/counties.json", "api/county/19169.json", "data/county/19169.csv", "data/state/ia.csv",
                    "data/county-land-index.csv", "data/counties-latest.csv", "data/status.json", "manifest.json"):
            self.assertTrue(os.path.exists(os.path.join(self.dist, rel)), rel)

    def test_county_page_states_values_from_the_data(self):
        page = self.read("iowa/story-county/index.html")
        self.assertIn("$10,914 per acre", page)
        est = "${:,}".format(int(round(10914 * fixtures.IA_SURVEY[2026] / fixtures.IA_SURVEY[2022], -2)))
        self.assertIn(est, page)
        self.assertIn("Not investment advice", page)
        self.assertIn('rel="canonical" href="%s/iowa/story-county/"' % config.BASE_URL, page)
        self.assertNotIn("noindex", page)

    def test_withheld_value_is_explained(self):
        page = self.read("iowa/adair-county/index.html")
        self.assertIn("withheld", page)

    def test_sitemap_and_robots(self):
        sm = self.read("sitemap.xml")
        self.assertIn("<loc>%s/iowa/story-county/</loc>" % config.BASE_URL, sm)
        self.assertIn("<lastmod>2099-01-01</lastmod>", sm)
        self.assertIn("Sitemap: %s/sitemap.xml" % config.BASE_URL, self.read("robots.txt"))

    def test_search_index_rows(self):
        rows = json.loads(self.read("api/counties.json"))
        story = [r for r in rows if r[0] == "19169"][0]
        self.assertEqual(story[4], "/iowa/story-county/")
        self.assertEqual(story[7], "e")

    def test_share_card_sources_exist_for_each_state(self):
        self.assertTrue(os.path.exists(os.path.join(self.dist, "_og", "default.html")))
        self.assertTrue(os.path.exists(os.path.join(self.dist, "_og", "state-ia.html")))

    def test_no_banned_wording_anywhere(self):
        for dirpath, _, files in os.walk(self.dist):
            for name in files:
                if name.endswith(".html") and "_og" not in dirpath:
                    text = check_dist.visible_text(open(os.path.join(dirpath, name), encoding="utf-8").read())
                    for pat in check_dist.BANNED:
                        self.assertIsNone(re.search(pat, text, re.I), (name, pat))

    def test_manifest_lists_every_page(self):
        pages = json.loads(self.read("manifest.json"))["pages"]
        self.assertIn("/iowa/story-county/", pages)
        self.assertIn("/", pages)

    def test_optional_keys_stay_off_by_default(self):
        page = self.read("index.html")
        if not config.SUPPORT_URL:
            self.assertNotIn("Support this index", page)
        if not config.GOATCOUNTER:
            self.assertNotIn("goatcounter", page)


if __name__ == "__main__":
    unittest.main()
