"""Weekly link check of the live site.

    python3 scripts/linkcheck.py [base_url]

1. Every URL in the sitemap must answer 200 (fails the run otherwise).
2. Every external link found on the main pages and a sample of county pages is fetched politely (one at a time,
   with a pause). A broken external link is reported as a warning, not a failure: agencies move pages and some
   refuse automated requests, and that must not hide the internal result.
Writes a report to $GITHUB_STEP_SUMMARY.
"""
import html
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from landindex import config  # noqa: E402

MAIN = ["/", "/states/", "/rankings/", "/methodology/", "/data/", "/about/", "/iowa/"]


def status(url, method="GET"):
    for i in range(3):
        try:
            req = urllib.request.Request(url, method=method, headers={"User-Agent": config.USER_AGENT})
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.status, resp.read() if method == "GET" else b""
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 410):
                return exc.code, b""
            last = exc.code
        except Exception as exc:
            last = str(exc)[:80]
        time.sleep(2 * (i + 1))
    return last, b""


def main(base):
    base = base.rstrip("/")
    lines = ["## Link check: %s" % base, ""]
    st, body = status(base + "/sitemap.xml")
    urls = re.findall(r"<loc>([^<]+)</loc>", body.decode("utf-8")) if st == 200 else []
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda u: (u, status(u, "HEAD")[0]), urls))
    broken = [(u, s) for u, s in results if s != 200]
    lines.append("- %s %d sitemap URLs, %d broken" % ("ok  " if urls and not broken else "FAIL", len(urls), len(broken)))
    for u, s in broken[:50]:
        lines.append("  - %s %s" % (s, u))

    pages = [base + p for p in MAIN] + random.Random(int(time.time() // 86400)).sample(urls, min(15, len(urls)))
    external = set()
    for p in pages:
        s, doc = status(p)
        for href in re.findall(r'href="(https?://[^"]+)"', doc.decode("utf-8", "replace")):
            href = html.unescape(href)
            if not href.startswith(base) and "goatcounter" not in href:
                external.add(href.split("#")[0])
    warn = []
    for href in sorted(external):
        s, _ = status(href)
        if s != 200:
            warn.append((href, s))
            print("::warning title=External link::%s answered %s" % (href, s))
        time.sleep(1)
    lines.append("- %s %d external links, %d not answering 200" % ("ok  " if not warn else "warn", len(external), len(warn)))
    for href, s in warn:
        lines.append("  - %s %s" % (s, href))
    text = "\n".join(lines)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(text + "\n")
    return 1 if (not urls or broken) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else config.BASE_URL))
