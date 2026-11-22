# DECISIONS

## 1. A research index, not a fund (settles "a research index first, or a real fund?")
Jack's note describes shares that track a land index and can be traded in for parcels. Those shares are securities,
and redemption in kind needs a fund structure ('40 Act, REIT and SEC questions) that only securities counsel can
design. The evaluator's fastest path was a published paper index. So v1 is a statistical index of public data, and
the public copy never calls it a fund, never mentions shares, returns or redemption, and carries "not investment
advice" on every page. A build-time guard (`scripts/check_dist.py`) fails the deploy if banned wording appears.
The repository keeps the name `land-index-fund` because the build brief fixed it; the public name is
"US County Land Index".

## 2. No waitlist for the redeemable-share concept
The prompt's v1 listed a waitlist page explaining the concept. Cut: collecting interest in an unregistered security
is itself a regulatory question, and a form needs a third-party account (Pages has no backend). Recorded as a key
in OPERATIONS.md.

## 3. Sources
- USDA NASS Quick Stats bulk file `qs.economics_YYYYMMDD.txt.gz` (no API key; the Quick Stats API needs one).
  One file has the census county values, the annual state survey and county cash rents. It is about 585 MB, so the
  refresh checks its URL, ETag and size first and downloads only when it changed, monthly plus weekly in August to
  October.
- FHFA Working Paper 19-01 land price workbook (experimental, residential land under single-family homes).
- US Census Bureau 2021 cartographic boundaries for maps. The 2021 vintage keeps Connecticut's eight counties, which
  is how USDA and FHFA still report.

## 4. Method
County farm real estate values exist only in census years. The annual series joins them with the state's annual
survey and closes the county's own gap geometrically across each five-year span, so it passes through both
observations. After the last census, the county moves with its state. Estimates are rounded to three significant
figures and always labelled. No estimates for Alaska and Hawaii (not in the annual survey) or where USDA withheld the
latest census value. FHFA residential values are shown next to the farm values, never blended into them.
Rankings use the latest census and, by default, only counties with at least 10,000 acres in farms.

## 5. Static site, standard library only
Python 3.9 standard library for the pipeline and the builder (an `.xlsx` reader is about 90 lines), plain JS on the
client, SVG charts and maps drawn at build time. No build tools to break, and the whole site builds in about
10 seconds.

## 6. Distribution
Machine channels only: 3,100 county pages that answer "land price per acre in X County" with real numbers, state
pages, rankings, a sitemap (picked up by the account's host-root robots.txt), canonical URLs, Dataset and
BreadcrumbList structured data, share cards per state, IndexNow pings of changed pages only, CSV/JSON downloads and
an embeddable county card (the share loop: every embed links back). Launched indexed: nothing else serves this
content under Jack's name.

## 7. Defaults chosen instead of asking
- Relationship to Landosaur (open question): separate sites. Landosaur's static edition can link to these county
  pages for price context later; no shared code.
- Domain: `grounded.to` is already serving a small page, so a subdomain (`index.grounded.to`) is proposed rather
  than replacing it. A separate domain-rollout session owns DNS.
