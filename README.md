# US County Land Index

Land values per acre for every US county, from official USDA and FHFA statistics, as a free static website that
updates itself.

**Live:** https://index.grounded.to/ (the first address, https://theguysaccount.github.io/land-index-fund/, redirects there)

- **County pages** (about 3,100): USDA Census of Agriculture value of farm land and buildings per acre for every census
  since 1997, an annual series that joins census years with the state's yearly USDA survey (estimates are labelled as
  estimates), county cash rents, FHFA residential land values, rank in state and nation, and neighbouring counties.
- **State pages** with a county map and a sortable table; **rankings**; a national map and series.
- **Downloads and API**: CSV for every county, state and the whole index; static JSON per county; an embeddable card.
- **Method**: every step is on the [method page](https://index.grounded.to/methodology/).

Not investment advice and not an appraisal. A statistical summary of public data.

## Run

Python 3.9+ with the standard library only. Node 22+ and Google Chrome only for the browser test and share images.

```bash
python3 -m landindex.build dist          # build the site from data/ into dist/
python3 scripts/check_dist.py dist        # the guard that runs before every deploy
```

Serve `dist/` under its base path to click through it locally:

```bash
mkdir -p /tmp/li-root && ln -sfn "$PWD/dist" /tmp/li-root/land-index-fund && python3 -m http.server 4651 --directory /tmp/li-root
```

Then open http://localhost:4651/land-index-fund/.

## Test

```bash
python3 -m unittest discover -s tests -t .
node scripts/e2e.mjs http://localhost:4651/land-index-fund    # headless Chrome: search, chart, sorting, embed, phone width
```

## Refresh the data

```bash
python3 -m landindex.refresh --work work    # downloads only what changed upstream (the USDA file is about 585 MB)
```

## Deploy

Pushing to `main` deploys through GitHub Actions (`.github/workflows/deploy.yml`). The data refresh, weekly checks
and keep-alive run on schedules. Everything that runs, and the keys for a custom domain, money and analytics, is in
[OPERATIONS.md](OPERATIONS.md).

## Layout

| Path | What |
|---|---|
| `landindex/sources.py` | Find, download, parse and validate the USDA and FHFA files |
| `landindex/refresh.py` | Refresh each source on its own and keep last good data |
| `landindex/model.py` | The index: county series, estimates, ranks |
| `landindex/pages.py`, `charts.py`, `maps.py` | Page templates, SVG charts and maps |
| `landindex/build.py` | Writes the whole site |
| `data/` | Extracts of the public sources (CSV), source status, county outlines |
| `site/` | CSS, client scripts, favicon, default share image, IndexNow key |
| `scripts/` | Guard, share images, IndexNow, health, link check, browser test |
| `tools/build_geo.py` | Rebuilds `data/geo/` from Census Bureau boundary files (by hand, rarely) |

## Licence

Code: MIT (see LICENSE). Data: USDA and FHFA data are US government works in the public domain; the files made here
are dedicated to the public domain under CC0 1.0. County outlines: US Census Bureau cartographic boundary files.

Questions and corrections: [open an issue](https://github.com/theguysaccount/land-index-fund/issues).
