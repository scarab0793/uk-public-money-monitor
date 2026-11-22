# Public Projects Tracker — requirements and methodology

## Citizen questions
- Which public projects are funded by my taxes?
- What was the first formally approved cost and completion date?
- How much has been spent so far? What is the latest forecast total cost?
- How much higher or lower is the forecast/final cost compared with the **original approved baseline**?
- Is the delivery date delayed, by how many months, and why?
- Which public body is accountable, which companies hold contracts, and which documented payments link to the project?

## Core calculations
Cost variance GBP = final outturn (if complete), otherwise latest forecast total, minus original approved budget.
Cost variance percent = 100 × variance / original approved budget; NULL when baseline is missing or zero.
Schedule variance = actual completion date (if complete), otherwise latest forecast completion, compared with original completion date.
Always distinguish **forecast** overrun/delay from **realised** overrun/delay. Show data as-of date and currency basis. Negative variances are underspends or early delivery, not errors.

## Important caveats
Changes in project scope, inflation, accounting basis, or a project being split/merged can invalidate a simplistic comparison. Record original scope, revisions and documented explanations. Never infer that all additional spending is waste. Do not treat project-level forecast and its constituent contracts/payments as additive. A contract award is not proof of payment.

## Discovery and evidence
Start with Infrastructure and Projects Authority / National Infrastructure and Service Transformation Authority (NISTA) government major projects portfolio, NAO project reports, departmental annual reports and accounts, public spending transparency datasets, Find a Tender, Contracts Finder, parliamentary reports and devolved government capital programmes. Coverage will vary and must be displayed explicitly.

## Search fields
Project name, identifier, responsible body, supplier, sector, UK nation, location, status, budget range, cost variance range, delay range, date and official source.

## Planned UI
Separate Projects tab, sortable searchable results table, source-linked project detail with budget timeline, delivery milestones, contracts and payment evidence. No fictional projects in production search results.

## Release acceptance criteria
1. At least one official source ingestion with documented provenance and a successful repeatable test.
2. Project records linked to immutable source metadata.
3. Baseline, forecast and actual values clearly separated.
4. Search and filter results reproducible by API.
5. No double counting of project budgets, awards and transactions.
