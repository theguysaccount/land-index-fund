# STATE

- Starting point: idea only. Two Apple Notes lines (June 2026) about a land index whose shares trade in for land; no
  code, data or partner. Nothing to reuse except the thesis.
- Built (2026-11-22): a static, self-refreshing index of US land values by county from USDA NASS (census, annual
  survey, cash rents) and FHFA residential land data. 3,115 counties, 51 state pages, rankings, method, data and
  API pages, national and state maps, CSV/JSON downloads, embeddable card, share cards.
- Works: build (about 10 s), guard over every page, 45 unit tests, headless-Chrome end-to-end test (search, chart
  hover, sorting, embed, 375 px phone width), GitHub Pages deploy with IndexNow, monthly/seasonal refresh with
  per-source fallbacks, weekly health and link checks with a staleness dispatch, keep-alive. The first scheduled
  weekly check fired on its own on 2026-11-22 and passed.
- Known limits: county values are averages of operator estimates; post-2022 values are state-moved estimates;
  Alaska is reported in five USDA areas; FHFA's series is experimental and last ran to 2022.
- Address: https://index.grounded.to since 2026-11-22 (moved by the domain-rollout session; github.io redirects).
- Not done (keys, see OPERATIONS.md): support link, analytics, Search Console.
- Reusable elsewhere: `landindex/xlsx.py` (stdlib .xlsx reader), `landindex/sources.py` (resumable download, NASS
  bulk parsing), `scripts/cdp.mjs` + `e2e.mjs` (Chrome test without dependencies), the SVG chart and map code.
