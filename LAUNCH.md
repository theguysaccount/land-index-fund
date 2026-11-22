# LAUNCH

## Live now
- https://theguysaccount.github.io/land-index-fund/ (GitHub Pages, deployed by `deploy.yml`). Indexed: robots
  allow, sitemap listed in the account's host-root robots.txt, IndexNow pinged on every deploy.

## Domain (a key; nothing has been changed)
`grounded.to` is the portfolio match. It is live on SiteGround today (a small "Grounded To" page), so the plan is
to build on top of it with a subdomain rather than replace it:

| Record | Host | Value |
|---|---|---|
| CNAME | `index` | `theguysaccount.github.io.` |

Then the four commands in OPERATIONS.md ("Custom domain"). If Jack prefers the apex later, the GitHub Pages apex
records are A `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153` and AAAA
`2606:50c0:8000::153` to `2606:50c0:8003::153`, which would replace what SiteGround serves, so that needs his
explicit decision.

## First 1,000 users (machine channels only; nothing is posted by a person)
1. **Search.** Each county page targets "[county] land price per acre", "[county] farmland value", "[county] cash
   rent per acre"; state pages target "[state] land prices by county". Sitemap and IndexNow are live; Search Console
   is a key.
2. **AI answers.** Plain-language sentences with the number, year and source in the first paragraph, open CSV/JSON
   and a citation line on every county page make the pages easy to quote.
3. **Data reuse.** The CSVs are mirrored in the GitHub repo (topics: land-prices, farmland, usda, open-data).
   Researchers and journalists who find the repo get a clean, documented dataset.
4. **Embeds.** County cards (`/embed/?fips=`) on farm, real-estate and local-news sites link back.
5. **Seasonal spike.** USDA's August release drives searches; the weekly August-October refresh makes the new
   numbers appear within days.

Search terms to watch: "farmland value per acre by county", "land price per acre [state]", "USDA land values 2026",
"cash rent per acre [county]".
