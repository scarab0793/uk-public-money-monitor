# UK Public Money Monitor — full searchable database specification

## Mission
Answer: How much does the UK public sector collect, from whom and through which taxes or contributions? Where does it spend the money, who receives it, and what is spent on the machinery of government itself?

## Scope
UK central government, devolved administrations, local authorities, public bodies, NHS and relevant public corporations. Revenue: PAYE income tax, self-assessment, NICs (employee, employer, self-employed), VAT, corporation tax, excise duties, stamp taxes, council tax, business rates, fees and other receipts. Expenditure: departmental programmes, welfare, health, education, defence, debt interest, procurement, grants, subsidies, salaries, pensions, administration and estates. Overseas: bilateral/multilateral aid, international contributions, defence assistance, overseas contracts, grants and transfers. Classify by recipient geography and purpose independently.

## User journeys
- Search any tax or spending category, organization, supplier, country, programme or fiscal year.
- Filter by UK nation, central/local tier, source, cash/accrual basis, estimate/actual, domestic/overseas.
- Drill down from national aggregate -> department -> programme -> award -> payment, only when a source-backed relationship exists.
- Compare nominal and inflation-adjusted values with explicitly selected deflators.
- Inspect the government's own operating costs: administration, staffing, ministerial/parliamentary expenses, buildings, consultants, IT, procurement. Expose classification definitions and uncertainty.
- Export results as CSV/JSON with provenance and reproducible query parameters.

## Data principles
1. Every published record has source provenance, publication/retrieval timestamps and reporting basis.
2. Preserve original currency and accounting units; document conversions.
3. Keep estimates, budgets, forecasts and actuals separate.
4. Avoid double counting: national totals, departmental totals and itemised payments are not additive; intergovernmental transfers need consolidation.
5. Separate funding commitment, contract award and actual payment; distinguish ODA from other overseas spending.
6. Unavailable individual payments remain unknown, never inferred from aggregate totals.
7. Provide corrections and revision history; immutable raw-source snapshots.
8. Political neutrality: publish facts and methodology, not judgments about spending merit.

## Official source families to integrate
ONS public sector finances, HM Treasury PESA and OSCAR/departmental accounts, HMRC tax receipts and statistics, DWP expenditure, NHS finance, local government revenue/expenditure returns, Scottish/Welsh/NI finance releases, UK government transparency spend files, Contracts Finder and Find a Tender, Companies House, FCDO/DevTracker and UK ODA statistical releases, MOD accounts and military assistance disclosures, NAO and devolved auditors.

## Implementation phases
1. **Foundation:** schema.sql, source registry, ingestion contracts, raw-file checksums, reproducible tests.
2. **Public finance aggregates:** verified ONS/HMRC/Treasury actuals with time-series and source links.
3. **Detailed spending:** departmental transparency transactions, contract awards and supplier identifiers.
4. **Overseas flows:** ODA, international organizations, military assistance and overseas procurement; distinguish pledges from disbursements.
5. **Government administration:** consistent cost taxonomy and breakdown by department and year.
6. **Nation/local coverage:** devolved and council datasets with comparable metadata.
7. **Search & API:** PostgreSQL full-text search, materialized rollups, filters, pagination, CSV exports, caching, automated validation and audit logs.

## Architecture
GitHub Actions collectors -> raw immutable snapshots -> validators and entity resolution -> PostgreSQL -> FastAPI query service -> responsive public website. Static GitHub Pages can host the UI and public snapshots in early phases, but not the complete transactional database and search backend. Large-scale search requires a hosted database/API.

## Quality gates
Reject unlabeled figures, invalid units, missing sources, duplicate source IDs, inconsistent periods and impossible currency conversion. Display coverage counts and data freshness per dataset; never claim exhaustive coverage where records are not published.
