# OPERATIONS

Everything that runs, how it fails safely, what to watch, and the keys a human can turn later.
Live site: https://theguysaccount.github.io/land-index-fund/ (public name: **US County Land Index**).

## Automated jobs

| Workflow | When | What it does | How it fails safely |
|---|---|---|---|
| `refresh.yml` Refresh data | 3rd of every month 07:41 UTC, and Mondays 07:41 UTC from August to October; or by hand (`force` re-extracts) | Finds the newest USDA NASS `qs.economics_*.txt.gz` and the newest FHFA land price workbook. Skips a source whose file (URL, ETag, size) is unchanged. Otherwise downloads it (5 tries, resumes), parses, validates, guards against shrinkage, and writes only the CSVs that changed. If anything in `data/` changed: tests, a full build and the guard run on the new data, then it commits and dispatches `deploy.yml`. | Each source runs on its own: a failure is retried, then that source keeps its last good extract and the run passes with a warning (`status.json` records `ok: false`, the message and a failure count). A failed test or build stops before any commit. A quiet check commits nothing. |
| `deploy.yml` Build and deploy | Pushes to `main` that touch code or data; dispatched by the refresh; by hand | Unit tests, build (about 3,200 pages, 9,500 files), the guard (`scripts/check_dist.py`), share images in headless Chrome, a browser test of the built site, then Pages deploy (a second attempt if the first stalls). After deploy it waits until the new build is served, runs the browser test on the live site and tells IndexNow about the pages whose content changed. | Anything failing before the deploy step leaves the last good deploy live. IndexNow never fails the run. |
| `checks.yml` Weekly checks | Thursdays 05:23 UTC; by hand | `scripts/health.py`: key pages and files answer; the live data matches the repository (dispatches a deploy if not); no source has failed 3 refreshes in a row; USDA's survey year is current; 25 sampled county pages answer; **staleness**: if no refresh has succeeded for 40 days it dispatches one, and fails at 70 days. `scripts/linkcheck.py`: every sitemap URL answers 200; external links are checked politely and only warn. The browser test runs on the live site. | Read-only apart from dispatching a refresh or deploy. A failure emails the repository owner. |
| `keepalive.yml` | Called by every scheduled workflow | Re-enables any workflow GitHub disabled for inactivity and pushes `.github/heartbeat` after 40 quiet days (GitHub disables schedules after 60). | Harmless when nothing is needed. |
| `ci.yml` | Every push and pull request | Unit tests on Python 3.10 and 3.13 (runners on Ubuntu 26.04 have no 3.9; the code stays 3.9-compatible), a full build plus guard, and a syntax check of the client scripts. | Read-only. |

Notes:
- GitHub fires schedules late on this account (hours, in batches). Nothing depends on exact timing: every job is safe to re-run, and the weekly staleness check dispatches a refresh when scheduled runs go missing.
- Schedules proven: the first schedule-triggered weekly check ran on 2026-11-22 (about 8 hours after the cron was added, as is usual on this account) and passed; the temporary proof line was then removed.

## What to watch

| Signal | Where | Healthy |
|---|---|---|
| Runs | Actions tab; failure emails to the owner of `theguysaccount` | Green; refresh mostly "Nothing new" |
| Source health | `/data/status.json` on the site, or `data/status.json` in the repo: `ok`, `failures`, `message`, `latest_survey_year`, `version` | `ok: true`, failures 0 |
| Freshness | Data page footer ("Data last updated"); `site.survey_year` in status.json | USDA's survey year is the current year from mid-August |
| Index coverage | Bing Webmaster Tools / IndexNow; Search Console once verified | Growing |
| Errors reported by people | GitHub issues | Answer each with the source figure |

## Release calendar (what to expect)

- **USDA Land Values** (state farm real estate, cropland, pasture): early August every year. The August/September weekly runs pick it up; county estimates for the new year appear automatically.
- **USDA Cash Rents** (county): late August or September, most years.
- **Census of Agriculture**: every five years. The 2027 census values are due in early 2029. When they land, new county observations replace the estimates; nothing in the code assumes 2022 is the last census.
- **FHFA land prices**: irregular. The workbook link on the working-paper page is found by name and date; if FHFA renames it beyond recognition the FHFA source fails safely and the warning shows in the run.

## Keys Jack can turn later

| Key | Why | Exact steps |
|---|---|---|
| **Custom domain** | Brand and trust; drops "land-index-fund" from the address | `grounded.to` is live on SiteGround (A 35.215.81.164) serving a small "Grounded To" page, so build on top rather than replacing it: use a subdomain such as `index.grounded.to`. (1) In Namecheap or SiteGround DNS for grounded.to, add `CNAME index -> theguysaccount.github.io.` (2) `~/.local/bin/gh api -X PUT repos/theguysaccount/land-index-fund/pages -f cname=index.grounded.to` (or Settings, Pages, Custom domain). (3) `~/.local/bin/gh variable set SITE_URL -R theguysaccount/land-index-fund -b https://index.grounded.to` (fleet convention; `LI_BASE_URL` also works) (4) `~/.local/bin/gh workflow run deploy.yml -R theguysaccount/land-index-fund`. (5) After the certificate is issued: `gh api -X PUT repos/theguysaccount/land-index-fund/pages -F https_enforced=true`. Canonicals, sitemap, robots.txt, JSON URLs and IndexNow all follow `SITE_URL`. GitHub serves the old github.io address as a redirect to the custom domain. |
| **Money: support link** | First revenue, without breaking Pages' non-commercial rule | Set up GitHub Sponsors for `theguysaccount` (needs Jack's identity, bank and tax details), then `gh variable set LI_SUPPORT_URL -R theguysaccount/land-index-fund -b https://github.com/sponsors/theguysaccount` and run `deploy.yml`. A "Support this index" link appears in the footer and on the About page. Any paid product (for example county reports) must be hosted off GitHub Pages. |
| **Analytics** | Measure the activation event (a county page view from search) | Create a GoatCounter site, then `gh variable set LI_GOATCOUNTER -b https://<code>.goatcounter.com/count` and redeploy. Cookieless. |
| **Google Search Console** | Google does not read IndexNow | Verify the site (HTML tag): `gh variable set LI_GOOGLE_VERIFY -b <token>`, redeploy, then submit `/sitemap.xml`. |
| **The redeemable-share idea** | Jack's original concept (shares that track the index and can be traded for land) | Not built on purpose: it is a security and a fund structure. It needs securities counsel first (see DECISIONS.md). Nothing on the site offers, describes or collects interest in such a product. |

## Scheduled Claude routine (optional)

No AI-written content is needed: every sentence is computed from the data. If someone wants a yearly review after USDA's August release, schedule a Claude Code routine in this repo with:

> In ~/code/land-index-fund (git pull):
> 1. Read `data/status.json` and the last 5 runs of refresh.yml and deploy.yml. If USDA's survey year is not the current year after 1 September, check https://www.nass.usda.gov/datasets and the FHFA page, and run `gh workflow run refresh.yml -f force=true`.
> 2. Spot-check five county pages against Quick Stats (quickstats.nass.usda.gov) in a browser.
> 3. Answer open issues with the source figure; fix code-level problems only, never hand-edit data.
> 4. Run the tests, commit, push. Do not post anywhere.

## Failure playbook

- **"Source kept on last good data" warning:** read the message in the run log or `status.json`. A timeout or 5xx usually clears by the next run. A validation or guard refusal means the file changed shape: look at the new file, adapt `landindex/sources.py`, add a test, push.
- **Guard (check_dist) failure in a deploy:** the message names the page and the problem (broken link, missing notice, banned wording, duplicate title). Fix the template in `landindex/pages.py`.
- **Live data does not match the repository:** the weekly check dispatches a deploy. If deploys keep failing, see the deploy run.
- **Pages size:** the build is about 130 MB of the 1 GB limit.
