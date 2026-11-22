# Importing official project data

The Public Projects Tracker accepts source-backed project records. It deliberately does **not** include sample projects as real results.

## Required CSV columns
`id,name,department,sector,status,source_url,source_title,source_as_of`

## Optional CSV columns
`nation,description,original_budget_gbp,current_forecast_gbp,actual_spend_gbp,original_completion,forecast_completion,actual_completion,notes`

Amounts must be nominal GBP, not GBP millions. Dates are ISO `YYYY-MM-DD`. Unknown amounts and dates must be blank, not zero. Each row needs a specific official source URL and the source's as-of date. Project scope changes must be explained in notes. A forecast is not a final outturn.

Run `python scripts/build_projects.py imports/official-projects.csv` after mapping an official publication into this schema. The command validates and publishes `data/projects.json`. The website reads that file and offers full-text filtering, sector/department filters, delay and cost variance calculations, and links to official evidence.

For UK Government Major Projects Portfolio (GMPP), first verify each annual dataset's column meanings and units. Map departmental returns and their project narratives carefully. Do not assume the figures are comparable between years or that disclosed whole-life costs equal payments made. Add devolved projects and local programmes using their own verified source documents.

**Coverage**: this is an importer and searchable frontend, not a complete UK-wide project database. Its coverage is only the imported records. An empty catalogue must be displayed as empty, not filled with examples.
