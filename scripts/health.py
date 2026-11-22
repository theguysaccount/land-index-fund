"""Weekly self-test of the live site, plus the staleness check that keeps refreshes from silently stopping.

    python3 scripts/health.py [base_url]

Fails (exit 1) when:
- a key page, file or a sample of county pages does not answer;
- the live site serves data older than the repository's (a deploy did not land);
- a source has failed three refreshes in a row;
- no refresh has succeeded for 70 days, or USDA's annual survey is more than a year behind.
Warns, and dispatches the refresh workflow, when no refresh has succeeded for 40 days (GitHub sometimes skips
scheduled runs). Needs GH_TOKEN and GITHUB_REPOSITORY for the workflow checks; without them those are skipped.
Writes a report to $GITHUB_STEP_SUMMARY.
"""
import datetime
import json
import os
import random
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from landindex import config, sources  # noqa: E402

KEY_PATHS = ["/", "/states/", "/rankings/", "/methodology/", "/data/", "/about/", "/iowa/", "/iowa/story-county/",
             "/embed/", "/sitemap.xml", "/robots.txt", "/api/counties.json", "/api/us.json", "/data/status.json",
             "/data/county-land-index.csv", "/assets/us-counties.svg", "/assets/app.js", "/og/default.png"]


def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url + ("&" if "?" in url else "?") + "selftest=%d" % int(time.time()),
                                         headers={"User-Agent": config.USER_AGENT})
            with urllib.request.urlopen(req, timeout=40) as resp:
                return resp.status, resp.read()
        except Exception as exc:
            last = exc
            time.sleep(3 * (i + 1))
    return str(last), b""


def gh(*args):
    out = subprocess.run(["gh"] + list(args), capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:300])
    return out.stdout


def main(base):
    base = base.rstrip("/")
    lines, failed = ["## Live site: %s" % base, ""], []
    today = datetime.datetime.now(datetime.timezone.utc).date()

    def report(ok, text, fatal=True):
        lines.append("- %s %s" % ("ok  " if ok else ("FAIL" if fatal else "warn"), text))
        if not ok and fatal:
            failed.append(text)
        if not ok and not fatal:
            print("::warning title=Self-test::%s" % text)

    key = open(os.path.join(ROOT, "site", "indexnow-key.txt")).read().strip()
    for p in KEY_PATHS + ["/%s.txt" % key]:
        st, body = get(base + p)
        report(st == 200 and len(body) > 20, "%s answers %s" % (p, st))

    st, body = get(base + "/data/status.json")
    live = json.loads(body) if st == 200 else {}
    repo = sources.load_status()
    live_changed = sorted(s.get("changed", "") for s in live.get("sources", {}).values())
    repo_changed = sorted(s.get("changed", "") for s in repo.get("sources", {}).values())
    report(live_changed == repo_changed, "live data matches the repository (live %s, repo %s)" % (live_changed, repo_changed))
    if live_changed != repo_changed and os.environ.get("GH_TOKEN"):
        try:
            gh("workflow", "run", "deploy.yml", "-R", os.environ["GITHUB_REPOSITORY"])
            lines.append("- info dispatched deploy.yml to catch the site up")
        except Exception as exc:
            lines.append("- warn could not dispatch deploy.yml: %s" % exc)
    for key_, s in sorted(repo.get("sources", {}).items()):
        report(int(s.get("failures") or 0) < 3, "%s: %s consecutive failed refreshes%s" % (
            s.get("label", key_), s.get("failures", 0), (" (" + s.get("message", "") + ")") if s.get("message") else ""))

    survey_year = int((live.get("site") or {}).get("survey_year") or 0)
    expected = today.year if today >= datetime.date(today.year, 9, 15) else today.year - 1
    report(survey_year >= expected - 1, "USDA survey year %s (a release for %d is expected by now)" % (survey_year, expected))
    if survey_year < expected:
        report(False, "USDA's %d land values survey is not in the data yet" % expected, fatal=False)

    st, body = get(base + "/api/counties.json")
    try:
        rows = json.loads(body)
        sample = random.Random(today.toordinal()).sample(rows, min(25, len(rows)))
        bad = []
        for r in sample:
            s2, page = get(base + r[4], tries=2)
            if s2 != 200 or r[1].encode("utf-8") not in page or b"Not investment advice" not in page:
                bad.append("%s (%s)" % (r[4], s2))
        report(not bad, "%d sampled county pages answer with their name and notice%s" % (len(sample), (": " + ", ".join(bad)) if bad else ""))
    except Exception as exc:
        report(False, "county sample: %s" % exc)

    repo_name = os.environ.get("GITHUB_REPOSITORY")
    if os.environ.get("GH_TOKEN") and repo_name:
        try:
            runs = json.loads(gh("run", "list", "-R", repo_name, "--workflow", "refresh.yml", "--status", "success",
                                 "--limit", "1", "--json", "createdAt"))
            if runs:
                last = datetime.datetime.strptime(runs[0]["createdAt"][:10], "%Y-%m-%d").date()
                age = (today - last).days
            else:
                age = None
            if age is None or age > 40:
                report(False, "no successful refresh for %s days: dispatching one" % (age if age is not None else "ever"), fatal=False)
                gh("workflow", "run", "refresh.yml", "-R", repo_name)
            else:
                report(True, "last successful refresh %d days ago" % age)
            if age is not None and age > 70:
                report(False, "no successful refresh for %d days" % age)
        except Exception as exc:
            report(False, "could not read workflow runs: %s" % exc, fatal=False)
    else:
        lines.append("- info workflow checks skipped (no GH_TOKEN)")

    text = "\n".join(lines)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(text + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else config.BASE_URL))
