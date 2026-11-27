# UK Public Money Monitor

Independent transparency site for UK public money: what the state collects, what it spends, who it pays, and how its major projects are going. Live at https://scarab0793.github.io/uk-public-money-monitor/

Every figure comes from an official publisher and links back to it. Data is refreshed automatically on GitHub Actions; nothing runs on paid services and no AI API is used in daily operation.

## What is on the site

| Module | Source | Data file | Refresh |
| --- | --- | --- | --- |
| Public contracts, suppliers and buyers | Contracts Finder and Find a Tender (OCDS) | `data/procurement/` | daily, plus historical backfill |
| HMRC tax receipts by tax, monthly and annual | HMRC | `data/hmrc/receipts.json` | daily check |
| Public spending by function | HM Treasury PSS (TES tables 9, 9a, 9b) | `data/treasury/pss-expenditure-on-services.json` | daily check |
| Spending by nation and English region | HM Treasury Country and Regional Analysis | `data/treasury/country-regional-analysis.json` | daily check |
| Benefit spending and caseloads, 1948-49 to forecast | DWP benefit expenditure and caseload tables | `data/welfare/benefit-expenditure-caseloads.json` | daily check |
| NHS trust and foundation trust accounts | NHS England TAC data | `data/nhs/trust-accounts.json` | daily check |
| NHS Wales spending by health condition | Welsh Government programme budgets (StatsWales API) | `data/nhs/wales-programme-budgets.json` | daily check |
| Government grants: departments, schemes, recipients, awards | Cabinet Office Government Grants Register | `data/grants/government-grants.json` | daily check |
| Council Tax bills by band | MHCLG | `data/local-government/council-tax-england.json` | daily check |
| Council spending by service, England | MHCLG revenue outturn (RSX) | `data/local-government/revenue-outturn-england.json` | daily check |
| Council spending by service, Wales | Welsh Government revenue outturn (StatsWales API) | `data/local-government/revenue-outturn-wales.json` | daily check |
| Overseas development assistance | FCDO / Statistics on International Development | `data/fcdo-normalized/` | weekly |
| Government major projects | NISTA annual reports (2025-26 verified against the official CSV) | `data/gmpp-*.json`, `data/nista-*.json` | weekly check |
| ONS public sector finances | ONS | `data/ons-*.json` | daily |
| Income Tax and NI calculator | GOV.UK rates pages | `data/tax/income-tax-rates.json` | checked by hand each tax year |

`data/catalogue.json` lists every dataset with its publisher, basis, unit, verification status and limitations, plus the modules that are not covered yet and why. The Sources section of the site is built from it.

## Rules the data follows

- Missing is never shown as zero. A council that did not file, a trust that did not exist, a withheld project cost all appear as "not available".
- Different measures are never added together: cash receipts and accrued revenue, outturn and forecast, nominal and real terms, contract values and payments, framework ceilings and call-offs.
- Estimates, budgets, tender values and framework maximums are labelled as such and never presented as spending.
- Suppliers are linked only through published identifiers (Companies House number and similar), never by name alone.
- A failed import keeps the last good data. Each importer validates its output (row counts, published totals, accounting identities) before replacing anything, and records the outcome in `data/official-tables-report.json` or the module's own report.

## How it runs

| Workflow | What it does |
| --- | --- |
| `procurement.yml` | Contracts Finder and Find a Tender import into monthly raw partitions (stored as assets of the `procurement-raw` release); only the import state is committed |
| `refresh-official-tables.yml` | HMRC, Treasury, DWP, NHS, MHCLG and grants tables (`scripts/import_official_tables.py`) |
| `import-fcdo.yml`, `normalize-fcdo.yml` | ODA data |
| `import-nista.yml` | major projects, including verification of the 2025-26 records |
| `pages.yml` | builds the procurement database (`data/procurement/notices`, `suppliers`, `buyers`, `summary.json`) from the raw archive and the site-wide search index (`data/search/`), then deploys the site to GitHub Pages. Runs on every push and after every data workflow; if a build or validation fails nothing is deployed and the previous site stays live |
| `explore-sources.yml` | diagnostic: lists a publication's attachments and previews spreadsheets |

Tests: `python -m unittest tests.test_procurement tests.test_official_tables`

The site is static (`index.html` plus `assets/js/`). The procurement database and search index are generated, not committed. To run it locally: `gh release download procurement-raw --pattern '*.ndjson.gz' --dir raw-procurement`, `python scripts/build_procurement.py`, `python scripts/build_search_index.py`, then serve the repository root (`python3 -m http.server`) and open http://localhost:8000.

## Known gaps

See "Not covered yet, and why" on the Sources section, or `gaps` in `data/catalogue.json`. In short: military aid has no official machine-readable series; NHS commissioners and the devolved health services, council spending in Scotland and Northern Ireland, and government pay and property are next.

The NHS England page that lists the trust accounts files refuses automated requests, so the file links for each new year are added to `data/nhs/tac-sources.json` when NHS England publishes them.

## Licence

Data is reused under the Open Government Licence v3.0 from the publishers named above.
