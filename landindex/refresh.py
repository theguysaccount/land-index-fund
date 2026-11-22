"""Refresh data/ from USDA NASS and FHFA. Safe to run at any time, any number of times.

    python3 -m landindex.refresh [--work DIR] [--force] [--nass-file qs.economics.txt.gz] [--fhfa-file book.xlsx]

For each source: find the current file, skip the download when it is the file already extracted, otherwise
download (with retries and resume), parse, validate, compare against the extract already in data/ and write
only what changed. A source that fails is retried inside this run, then left on its last good extract and
reported in data/status.json and as a workflow warning. The exit code is 0 unless the run itself is broken,
so one unreachable agency never blocks the other or the deploy.

Prints `changed=true|false` (also to $GITHUB_OUTPUT) so the workflow knows whether to rebuild the site.
"""
import argparse
import datetime
import os
import sys
import tempfile

from . import config, sources
from .sources import SourceError


def _today():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _write_changed(tables, names, data_dir):
    """Write each table whose CSV text differs from the file on disk. Returns (changed names, sha256 by name)."""
    changed, digests = [], {}
    for name in names:
        text = sources.csv_text(name, tables[name])
        digests[name] = sources.sha256_text(text)
        path = os.path.join(data_dir, name)
        old = None
        if os.path.exists(path):
            with open(path, encoding="utf-8", newline="") as fh:
                old = fh.read()
        if old != text:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            changed.append(name)
    return changed, digests


def guard_usda(new, data_dir):
    """Refuse an extract that lost data compared with the one already published."""
    problems = []
    old_county = sources.read_csv("usda_county_land_value.csv", data_dir)
    old_survey = sources.read_csv("usda_state_land_value.csv", data_dir)
    old_rent = sources.read_csv("usda_county_cash_rent.csv", data_dir)
    new_county, new_survey = new["usda_county_land_value.csv"], new["usda_state_land_value.csv"]
    new_rent = new["usda_county_cash_rent.csv"]
    if old_county:
        if len(new_county) < 0.98 * len(old_county):
            problems.append("county land value rows fell from %d to %d" % (len(old_county), len(new_county)))
        lost = {r["year"] for r in old_county} - {r["year"] for r in new_county}
        if lost:
            problems.append("census years disappeared: %s" % ", ".join(sorted(lost)))
    if old_survey:
        if len(new_survey) < 0.98 * len(old_survey):
            problems.append("state survey rows fell from %d to %d" % (len(old_survey), len(new_survey)))
        if max(r["year"] for r in new_survey) < max(r["year"] for r in old_survey):
            problems.append("the latest survey year went backwards")
    if old_rent and len(new_rent) < 0.9 * len(old_rent):
        problems.append("county cash rent rows fell from %d to %d" % (len(old_rent), len(new_rent)))
    if problems:
        raise SourceError("USDA extract refused: " + "; ".join(problems))


def guard_fhfa(new, data_dir):
    problems = []
    old_panel = sources.read_csv("fhfa_county_panel.csv", data_dir)
    old_cs = sources.read_csv("fhfa_county_cross_section.csv", data_dir)
    new_panel, new_cs = new["fhfa_county_panel.csv"], new["fhfa_county_cross_section.csv"]
    if old_panel:
        old_n, new_n = len({r["fips"] for r in old_panel}), len({r["fips"] for r in new_panel})
        if new_n < 0.9 * old_n:
            problems.append("panel counties fell from %d to %d" % (old_n, new_n))
        if max(r["year"] for r in new_panel) < max(r["year"] for r in old_panel):
            problems.append("the latest panel year went backwards")
    if old_cs and len(new_cs) < 0.9 * len(old_cs):
        problems.append("cross-section counties fell from %d to %d" % (len(old_cs), len(new_cs)))
    if problems:
        raise SourceError("FHFA extract refused: " + "; ".join(problems))


def _same_file(entry, info):
    return bool(entry.get("etag") and entry.get("url") == info["url"] and entry.get("etag") == info["etag"]
                and entry.get("bytes") == info["bytes"])


def refresh_usda(data_dir, work, entry, force=False, local=None, log=print):
    info = {}
    if local:
        path = local
        info = {"url": entry.get("url", ""), "note": "extracted from a local file"}
    else:
        url, stamp = sources.find_nass_economics(sources.fetch_text(sources.NASS_LISTING))
        info = sources.head(url)
        info["file_date"] = stamp
        have_all = all(os.path.exists(os.path.join(data_dir, n)) for n in sources.NASS_FILES)
        if not force and have_all and _same_file(entry, info):
            log("USDA: %s is the file already extracted" % url)
            return [], info
        path = os.path.join(work, "qs.economics.txt.gz")
        if os.path.exists(path) and os.path.getsize(path) > info["bytes"] > 0:
            os.remove(path)
        log("USDA: downloading %s (%.0f MB)" % (url, info["bytes"] / 1e6))
        sources.download(url, path, expect_bytes=info["bytes"], log=log)
    tables = sources.validate_nass(sources.parse_nass_file(path))
    guard_usda(tables, data_dir)
    changed, digests = _write_changed(tables, sources.NASS_FILES, data_dir)
    county, survey = tables["usda_county_land_value.csv"], tables["usda_state_land_value.csv"]
    info.update({
        "sha256": digests,
        "rows": {n: len(tables[n]) for n in sources.NASS_FILES},
        "latest_census_year": max(r["year"] for r in county),
        "latest_survey_year": max(r["year"] for r in survey if r.get("farm_real_estate")),
        "latest_rent_year": max([r["year"] for r in tables["usda_county_cash_rent.csv"]] or [""]),
    })
    return changed, info


def refresh_fhfa(data_dir, work, entry, force=False, local=None, log=print):
    if local:
        path = local
        info = {"url": entry.get("url", ""), "note": "extracted from a local file"}
    else:
        url = sources.find_fhfa_workbook(sources.fetch_text(sources.FHFA_PAGE))
        info = sources.head(url)
        have_all = all(os.path.exists(os.path.join(data_dir, n)) for n in sources.FHFA_FILES)
        if not force and have_all and _same_file(entry, info):
            log("FHFA: %s is the workbook already extracted" % url)
            return [], info
        path = os.path.join(work, "fhfa-land-prices.xlsx")
        if os.path.exists(path):
            os.remove(path)
        log("FHFA: downloading %s (%.1f MB)" % (url, info["bytes"] / 1e6))
        sources.download(url, path, expect_bytes=info["bytes"], log=log)
    tables, version = sources.parse_fhfa(path)
    sources.validate_fhfa(tables)
    guard_fhfa(tables, data_dir)
    changed, digests = _write_changed(tables, sources.FHFA_FILES, data_dir)
    panel = tables["fhfa_county_panel.csv"]
    info.update({
        "sha256": digests,
        "rows": {n: len(tables[n]) for n in sources.FHFA_FILES},
        "version": version,
        "first_year": min(r["year"] for r in panel),
        "latest_year": max(r["year"] for r in panel),
    })
    return changed, info


def _without_checks(status):
    """The status minus the fields that change on every run."""
    import copy
    s = copy.deepcopy(status)
    s.pop("checked", None)
    for entry in s.get("sources", {}).values():
        entry.pop("checked", None)
        entry.pop("last_ok", None)
    return s


JOBS = (("usda", "USDA NASS Quick Stats", refresh_usda), ("fhfa", "FHFA residential land prices", refresh_fhfa))


def run(data_dir=None, work=None, force=False, local=None, today=None, log=print, jobs=JOBS):
    """Refresh every source. Returns (list of changed data files, list of warnings)."""
    data_dir = data_dir or config.DATA
    os.makedirs(data_dir, exist_ok=True)
    today = today or _today()
    local = local or {}
    status = sources.load_status(data_dir)
    status.setdefault("sources", {})
    before = _without_checks(status)
    changed_all, warnings = [], []
    made = None
    if work is None:
        made = work = tempfile.mkdtemp(prefix="land-index-")
    os.makedirs(work, exist_ok=True)
    for key, label, job in jobs:
        entry = status["sources"].setdefault(key, {})
        entry["label"] = label
        entry["checked"] = today
        try:
            changed, info = job(data_dir, work, entry, force=force, local=local.get(key), log=log)
        except Exception as exc:  # SourceError, or a parser surprise: either way keep the last good extract
            entry["ok"] = False
            entry["failures"] = int(entry.get("failures") or 0) + 1
            entry["message"] = "%s: %s" % (type(exc).__name__, exc)
            warnings.append("%s kept its last good data (%s)" % (label, entry["message"]))
            continue
        entry.update(info)
        entry.update({"ok": True, "failures": 0, "message": "", "last_ok": today})
        if changed:
            entry["changed"] = today
            changed_all.extend(changed)
            log("%s: updated %s" % (label, ", ".join(changed)))
        else:
            log("%s: no change" % label)
    status["checked"] = today
    # A check that found nothing new changes only the "checked" dates: leave the file alone, so the scheduled job
    # makes no commit. Anything else (new data, a new upstream file, a failure or a recovery) is recorded.
    if changed_all or _without_checks(status) != before or not os.path.exists(os.path.join(data_dir, "status.json")):
        sources.save_status(status, data_dir)
    if made:
        for name in os.listdir(made):
            os.remove(os.path.join(made, name))
        os.rmdir(made)
    return changed_all, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", default=config.DATA)
    ap.add_argument("--work", default=None, help="download folder (default: a temporary one)")
    ap.add_argument("--force", action="store_true", help="download and extract even if the files look unchanged")
    ap.add_argument("--nass-file", help="extract this local qs.economics file instead of downloading")
    ap.add_argument("--fhfa-file", help="extract this local workbook instead of downloading")
    args = ap.parse_args(argv)
    local = {k: v for k, v in (("usda", args.nass_file), ("fhfa", args.fhfa_file)) if v}
    changed, warnings = run(args.data, args.work, args.force, local)
    for w in warnings:
        print("::warning title=Source kept on last good data::%s" % w)
    lines = ["changed=%s" % ("true" if changed else "false"), "warnings=%d" % len(warnings)]
    print("\n".join(lines))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            fh.write("\n".join(lines) + "\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write("## Data refresh\n\n- changed files: %s\n" % (", ".join(changed) or "none"))
            for w in warnings:
                fh.write("- warning: %s\n" % w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
