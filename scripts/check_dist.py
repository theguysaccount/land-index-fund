"""Guard a built site before it is deployed. Exit 1 with a list of problems, or 0.

    python3 scripts/check_dist.py [dist]

Checks every HTML page: title, description, canonical, one h1, the not-investment-advice notice, valid JSON-LD,
no banned investment-product wording in visible text, and that every internal link and asset resolves to a file in
dist. Checks that the sitemap lists only pages that exist, that every county in the data has a page and a JSON file,
and that page titles and canonicals are unique. Nothing here pins a count or a date: expectations come from data/.
"""
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from landindex import config  # noqa: E402
from landindex.model import Index  # noqa: E402

# Public copy rules: this is a statistical index, not a financial product.
BANNED = [r"\bfunds?\b", r"\breturns?\b", r"\bredeem", r"\bguarantee", r"\bbuy shares\b", r"\binvestment opportunit",
          r"\bprofits?\b", r"\boutperform"]
NOTICE = "Not investment advice"
HREF = re.compile(r'(?:href|src|data)="([^"]+)"')


def visible_text(doc):
    doc = re.sub(r"(?is)<(script|style|svg)[^>]*>.*?</\1>", " ", doc)
    doc = re.sub(r"(?s)<[^>]+>", " ", doc)
    # URLs are not copy: the repository (and so the GitHub Pages path) is named land-index-fund.
    return re.sub(r"https?://\S+", " ", html.unescape(doc))


def resolve(dist, base, url):
    """dist file for an internal URL, or None for external/anchor links."""
    if url.startswith(config.BASE_URL):
        url = base + url[len(config.BASE_URL):]
    if not url.startswith(base + "/") and url != base:
        return None
    path = url[len(base):].split("#")[0].split("?")[0] or "/"
    rel = path.lstrip("/")
    if path.endswith("/"):
        rel += "index.html"
    return os.path.join(dist, rel)


def main(dist):
    base = config.base_path()
    problems = []
    titles, canon = {}, {}
    pages = 0
    for dirpath, _, files in os.walk(dist):
        for name in files:
            if not name.endswith(".html") or "/_og" in dirpath:
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, dist)
            doc = open(full, encoding="utf-8").read()
            pages += 1
            special = rel in ("embed/index.html", "404.html")
            t = re.search(r"<title>(.*?)</title>", doc, re.S)
            if not t or not t.group(1).strip():
                problems.append("%s: no title" % rel)
            elif not special:
                titles.setdefault(t.group(1), []).append(rel)
            if not special:
                if '<meta name="description" content="' not in doc or 'content=""' in doc.split("<body", 1)[0]:
                    problems.append("%s: missing or empty description" % rel)
                c = re.search(r'<link rel="canonical" href="([^"]+)"', doc)
                if not c:
                    problems.append("%s: no canonical" % rel)
                else:
                    canon.setdefault(c.group(1), []).append(rel)
                if doc.count("<h1") != 1:
                    problems.append("%s: %d h1 elements" % (rel, doc.count("<h1")))
                if NOTICE not in doc:
                    problems.append("%s: no not-investment-advice notice" % rel)
                if 'content="noindex' in doc and rel != "404.html":
                    problems.append("%s: noindex on an indexable page" % rel)
            for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', doc, re.S):
                try:
                    json.loads(block)
                except ValueError as exc:
                    problems.append("%s: bad JSON-LD (%s)" % (rel, exc))
            text = visible_text(doc)
            for pat in BANNED:
                m = re.search(pat, text, re.I)
                if m:
                    start = max(0, m.start() - 40)
                    problems.append("%s: banned wording %r in “%s”" % (rel, m.group(0), " ".join(text[start:m.end() + 40].split())))
            for url in HREF.findall(doc):
                url = html.unescape(url)
                target = resolve(dist, base, url)
                if target and not os.path.exists(target):
                    problems.append("%s: broken internal link %s" % (rel, url))
    for t, where in titles.items():
        if len(where) > 1:
            problems.append("duplicate title %r on %s" % (t, ", ".join(where[:3])))
    for c, where in canon.items():
        if len(where) > 1:
            problems.append("duplicate canonical %s on %s" % (c, ", ".join(where[:3])))

    sitemap = open(os.path.join(dist, "sitemap.xml"), encoding="utf-8").read()
    locs = re.findall(r"<loc>([^<]+)</loc>", sitemap)
    for loc in locs:
        target = resolve(dist, base, html.unescape(loc))
        if not target or not os.path.exists(target):
            problems.append("sitemap lists a missing page: %s" % loc)
    if "Sitemap: %s/sitemap.xml" % config.BASE_URL not in open(os.path.join(dist, "robots.txt")).read():
        problems.append("robots.txt does not point at the sitemap")

    ix = Index()
    for fips, c in ix.counties.items():
        if not os.path.exists(resolve(dist, base, base + ix.county_path(c))):
            problems.append("county %s (%s) has no page" % (fips, c["label"]))
        if not os.path.exists(os.path.join(dist, "api", "county", fips + ".json")):
            problems.append("county %s has no JSON" % fips)
    search = json.load(open(os.path.join(dist, "api", "counties.json")))
    if len(search) != len(ix.counties):
        problems.append("search index has %d counties, data has %d" % (len(search), len(ix.counties)))
    key = open(os.path.join(ROOT, "site", "indexnow-key.txt")).read().strip()
    if not os.path.exists(os.path.join(dist, key + ".txt")):
        problems.append("IndexNow key file missing")

    print("checked %d HTML files, %d sitemap URLs, %d counties: %d problems" % (pages, len(locs), len(ix.counties), len(problems)))
    for p in problems[:200]:
        print("  " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist")))
