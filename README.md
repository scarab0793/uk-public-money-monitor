# UK Public Money Monitor

Independent UK public finance transparency project. Prototype v0.1.

## Current capabilities
- Responsive standalone dashboard
- Tax calculator for standard 2025/26 England, Wales and Northern Ireland employment income (approximation)
- Four-nation navigation
- Links to official sources
- Explicit data provenance notice; no fabricated spending numbers

## Roadmap
1. Automated ingestion of ONS/HMRC/OBR and Treasury datasets, preserving source URL, publication date, retrieval time and revisions.
2. Separate Scotland, Wales, Northern Ireland and English local-government sources; NHS accounting.
3. Standardize fiscal years, geography, accounting bases, currencies and price bases.
4. Consolidate intergovernmental transfers to avoid double counting.
5. Integrate Find a Tender, Contracts Finder, Companies House and NAO audits with verifiable entity matching.
6. Versioned PostgreSQL database and automated validation tests; expose documented public API.
7. Source-linked charts, CSV exports, historical views and discrepancy reporting.

## Run
Open index.html in a browser, or serve this repository with GitHub Pages (Settings > Pages > Deploy from a branch > main / root).

## Caveats
No live dataset ingestion is implemented yet. The calculator is illustrative and omits pensions, benefits, student loans, salary sacrifice, Scottish rates, tax-code variations and other special circumstances. Verify tax-year rules before production use.
