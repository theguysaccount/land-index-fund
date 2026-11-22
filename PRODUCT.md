# PRODUCT

**User.** People who need a defensible number for "what is land worth around here": rural buyers and sellers sizing
an offer, farmers negotiating rent, appraisal and lending staff wanting a public reference, journalists, students
and researchers, and anyone curious about land as an asset.

**Painful job.** The official numbers exist but are buried: USDA's county land values sit in a 585 MB file or a
query tool, only every five years; the annual figures are state-level; FHFA's land data is a 17 MB spreadsheet.
Paid tools (AcreValue, LandApp, broker reports) put county figures behind sign-ups.

**Promise.** Type a county, get its land value per acre, how it moved, what renters pay and how it compares, with
every number traceable to its official source, free.

**Wedge.** County-level search queries ("Story County Iowa land price per acre", "cash rent per acre Lancaster
County") answered by a page with the actual numbers, trend and sources, plus open CSV/JSON that AI answers and
researchers can cite.

**Why now.** USDA's 2026 land values survey is out (US farm real estate hit a record) while the 2022 census is
the newest county snapshot; the gap between the two is exactly what this index fills, and it refreshes itself.

**Activation metric.** A visitor reaches a county page and stays (or downloads/copies its data). Instrumented once
`LI_GOATCOUNTER` is set (see OPERATIONS.md); until then, Bing/Search Console impressions on county pages.

**First revenue event.** A sponsor through the support link (GitHub Sponsors), turned on by one repository
variable. Later, off Pages: paid county reports or a data API for lenders and appraisers.

**What v1 deliberately won't do.** No fund, shares, returns, forecasts or advice. No parcel-level valuations or
appraisals. No user accounts, waitlists or email capture. No listings (that is Landosaur).
