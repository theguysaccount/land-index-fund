import os
import shutil
import tempfile
import unittest

from landindex import refresh, sources
from landindex.sources import SourceError
from tests import fixtures


class RefreshTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data = os.path.join(self.tmp, "data")
        fixtures.make_data_dir(self.data, self.tmp)
        self.quiet = lambda *a: None

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def snapshot(self):
        out = {}
        for n in sources.FILES:
            with open(os.path.join(self.data, n)) as fh:
                out[n] = fh.read()
        return out

    def test_a_failing_source_keeps_its_last_good_data_and_the_other_still_runs(self):
        before = self.snapshot()
        calls = []

        def broken(data_dir, work, entry, force=False, local=None, log=None):
            raise SourceError("site down")

        def fine(data_dir, work, entry, force=False, local=None, log=None):
            calls.append("fine")
            return [], {"url": "https://example.test/file", "etag": "abc", "bytes": 1}

        changed, warnings = refresh.run(self.data, os.path.join(self.tmp, "w"), today="2099-02-01", log=self.quiet,
                                        jobs=(("usda", "USDA", broken), ("fhfa", "FHFA", fine)))
        self.assertEqual(changed, [])
        self.assertEqual(calls, ["fine"])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(self.snapshot(), before)
        status = sources.load_status(self.data)
        self.assertFalse(status["sources"]["usda"]["ok"])
        self.assertEqual(status["sources"]["usda"]["failures"], 1)
        self.assertIn("site down", status["sources"]["usda"]["message"])
        self.assertTrue(status["sources"]["fhfa"]["ok"])
        self.assertEqual(status["sources"]["fhfa"]["etag"], "abc")
        # a second failure counts up; a success resets the count
        refresh.run(self.data, os.path.join(self.tmp, "w"), today="2099-02-08", log=self.quiet,
                    jobs=(("usda", "USDA", broken),))
        self.assertEqual(sources.load_status(self.data)["sources"]["usda"]["failures"], 2)
        refresh.run(self.data, os.path.join(self.tmp, "w"), today="2099-02-15", log=self.quiet,
                    jobs=(("usda", "USDA", fine),))
        st = sources.load_status(self.data)["sources"]["usda"]
        self.assertEqual((st["ok"], st["failures"], st["message"], st["last_ok"]), (True, 0, "", "2099-02-15"))

    def test_an_unexpected_parser_error_is_contained(self):
        def boom(*a, **k):
            raise KeyError("new column layout")
        changed, warnings = refresh.run(self.data, os.path.join(self.tmp, "w"), today="2099-02-01", log=self.quiet,
                                        jobs=(("fhfa", "FHFA", boom),))
        self.assertEqual(changed, [])
        self.assertIn("KeyError", warnings[0])

    def test_guard_refuses_shrinking_or_backward_data(self):
        nass = os.path.join(self.tmp, "qs.txt.gz")
        fixtures.write_nass_gz(nass)
        tables = sources.parse_nass_file(nass)
        refresh.guard_usda(tables, self.data)  # same data passes
        smaller = dict(tables)
        smaller["usda_county_land_value.csv"] = tables["usda_county_land_value.csv"][:1]
        with self.assertRaises(SourceError):
            refresh.guard_usda(smaller, self.data)
        older = dict(tables)
        older["usda_state_land_value.csv"] = [r for r in tables["usda_state_land_value.csv"] if r["year"] != "2026"]
        with self.assertRaises(SourceError):
            refresh.guard_usda(older, self.data)

    def test_only_changed_files_are_written(self):
        nass = os.path.join(self.tmp, "qs.txt.gz")
        fixtures.write_nass_gz(nass)
        tables = sources.parse_nass_file(nass)
        changed, digests = refresh._write_changed(tables, sources.NASS_FILES, self.data)
        self.assertEqual(changed, [])
        tables["usda_state_cash_rent.csv"] = tables["usda_state_cash_rent.csv"] + [{"state": "IA", "year": "2027", "cropland": "300"}]
        changed, _ = refresh._write_changed(tables, sources.NASS_FILES, self.data)
        self.assertEqual(changed, ["usda_state_cash_rent.csv"])

    def test_local_files_run_the_real_parsers_end_to_end(self):
        nass = os.path.join(self.tmp, "qs.txt.gz")
        fhfa = os.path.join(self.tmp, "fhfa.xlsx")
        fixtures.write_nass_gz(nass)
        fixtures.write_fhfa_xlsx(fhfa)
        # the synthetic files are far too small for validation: both sources must fail safely, data unchanged
        before = self.snapshot()
        changed, warnings = refresh.run(self.data, os.path.join(self.tmp, "w"), today="2099-03-01", log=self.quiet,
                                        local={"usda": nass, "fhfa": fhfa})
        self.assertEqual(changed, [])
        self.assertEqual(len(warnings), 2)
        self.assertEqual(self.snapshot(), before)


class QuietRunTest(unittest.TestCase):
    def test_a_check_that_finds_nothing_new_leaves_status_untouched(self):
        tmp = tempfile.mkdtemp()
        try:
            data = fixtures.make_data_dir(os.path.join(tmp, "data"), tmp)
            same = lambda *a, **k: ([], {"url": "u", "etag": "e", "bytes": 1})  # noqa: E731
            refresh.run(data, os.path.join(tmp, "w"), today="2099-04-01", log=lambda *a: None, jobs=(("usda", "USDA", same),))
            with open(os.path.join(data, "status.json")) as fh:
                first = fh.read()
            refresh.run(data, os.path.join(tmp, "w"), today="2099-05-01", log=lambda *a: None, jobs=(("usda", "USDA", same),))
            with open(os.path.join(data, "status.json")) as fh:
                self.assertEqual(fh.read(), first)
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
