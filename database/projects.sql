-- Project tracking extension for UK Public Money Monitor.
-- Monetary amounts are nominal GBP. NULL means unknown, never zero.
CREATE TABLE IF NOT EXISTS public_projects (
 id BIGSERIAL PRIMARY KEY,
 project_code TEXT UNIQUE,
 project_name TEXT NOT NULL,
 description TEXT,
 lead_entity_id BIGINT REFERENCES entities(id),
 delivery_entity_id BIGINT REFERENCES entities(id),
 uk_nation TEXT,
 location_description TEXT,
 sector TEXT,
 status TEXT NOT NULL DEFAULT 'unknown',
 original_approved_budget_gbp NUMERIC(22,2),
 current_approved_budget_gbp NUMERIC(22,2),
 latest_forecast_total_gbp NUMERIC(22,2),
 actual_spend_to_date_gbp NUMERIC(22,2),
 final_outturn_gbp NUMERIC(22,2),
 original_completion_date DATE,
 revised_completion_date DATE,
 actual_completion_date DATE,
 baseline_approval_date DATE,
 latest_report_date DATE,
 source_id BIGINT NOT NULL REFERENCES sources(id),
 methodology_notes TEXT,
 CONSTRAINT project_costs_nonnegative CHECK (
 (original_approved_budget_gbp IS NULL OR original_approved_budget_gbp >= 0)
 AND (current_approved_budget_gbp IS NULL OR current_approved_budget_gbp >= 0)
 AND (latest_forecast_total_gbp IS NULL OR latest_forecast_total_gbp >= 0)
 AND (actual_spend_to_date_gbp IS NULL OR actual_spend_to_date_gbp >= 0)
 AND (final_outturn_gbp IS NULL OR final_outturn_gbp >= 0))
);
CREATE TABLE IF NOT EXISTS project_updates (
 id BIGSERIAL PRIMARY KEY,
 project_id BIGINT NOT NULL REFERENCES public_projects(id),
 as_of_date DATE NOT NULL,
 approved_budget_gbp NUMERIC(22,2),
 forecast_total_gbp NUMERIC(22,2),
 spend_to_date_gbp NUMERIC(22,2),
 forecast_completion_date DATE,
 status TEXT,
 explanation TEXT,
 source_id BIGINT NOT NULL REFERENCES sources(id),
 UNIQUE(project_id, as_of_date, source_id)
);
CREATE TABLE IF NOT EXISTS project_contracts (
 project_id BIGINT NOT NULL REFERENCES public_projects(id),
 contract_reference TEXT NOT NULL,
 supplier_entity_id BIGINT REFERENCES entities(id),
 award_value_gbp NUMERIC(22,2),
 source_id BIGINT NOT NULL REFERENCES sources(id),
 PRIMARY KEY(project_id,contract_reference)
);
CREATE TABLE IF NOT EXISTS project_record_links (
 project_id BIGINT NOT NULL REFERENCES public_projects(id),
 record_id BIGINT NOT NULL REFERENCES records(id),
 relationship TEXT NOT NULL CHECK(relationship IN ('payment','grant','allocation','contract_payment')),
 PRIMARY KEY(project_id,record_id,relationship)
);
CREATE INDEX IF NOT EXISTS public_projects_search_idx ON public_projects USING gin (
 to_tsvector('english', coalesce(project_name,'') || ' ' || coalesce(description,'') || ' ' || coalesce(sector,''))
);
CREATE INDEX IF NOT EXISTS public_projects_sector_idx ON public_projects(sector,status,uk_nation);
CREATE VIEW project_variances AS SELECT p.*,
 COALESCE(p.final_outturn_gbp,p.latest_forecast_total_gbp)-p.original_approved_budget_gbp AS variance_gbp,
 CASE WHEN p.original_approved_budget_gbp > 0 THEN
  100*(COALESCE(p.final_outturn_gbp,p.latest_forecast_total_gbp)-p.original_approved_budget_gbp)/p.original_approved_budget_gbp
 ELSE NULL END AS variance_percent,
 CASE WHEN COALESCE(p.actual_completion_date,p.revised_completion_date) IS NOT NULL AND p.original_completion_date IS NOT NULL
 THEN (EXTRACT(YEAR FROM age(COALESCE(p.actual_completion_date,p.revised_completion_date),p.original_completion_date))*12
 + EXTRACT(MONTH FROM age(COALESCE(p.actual_completion_date,p.revised_completion_date),p.original_completion_date)))
 ELSE NULL END AS schedule_variance_months
 FROM public_projects p;
