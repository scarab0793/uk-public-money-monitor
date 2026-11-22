-- UK Public Money Monitor: canonical public finance ledger schema (PostgreSQL)
-- Amounts are signed GBP values; raw currencies are preserved.
CREATE TABLE IF NOT EXISTS sources (
 id BIGSERIAL PRIMARY KEY, publisher TEXT NOT NULL, title TEXT NOT NULL,
 source_url TEXT NOT NULL, publication_date DATE, retrieved_at TIMESTAMPTZ NOT NULL,
 licence TEXT, sha256 CHAR(64), document_type TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS entities (
 id BIGSERIAL PRIMARY KEY, canonical_name TEXT NOT NULL, entity_type TEXT NOT NULL,
 jurisdiction TEXT, companies_house_number TEXT, charity_number TEXT,
 parent_entity_id BIGINT REFERENCES entities(id),
 UNIQUE (canonical_name, entity_type, jurisdiction)
);
CREATE TABLE IF NOT EXISTS records (
 id BIGSERIAL PRIMARY KEY,
 record_kind TEXT NOT NULL CHECK(record_kind IN ('revenue','expenditure','transfer','borrowing','debt_interest')),
 granularity TEXT NOT NULL CHECK(granularity IN ('transaction','aggregate','estimate')),
 reporting_basis TEXT NOT NULL CHECK(reporting_basis IN ('cash','accrual','budget','forecast','unknown')),
 fiscal_year TEXT, period_start DATE, period_end DATE,
 paying_entity_id BIGINT REFERENCES entities(id),
 receiving_entity_id BIGINT REFERENCES entities(id),
 category TEXT NOT NULL, subcategory TEXT, purpose TEXT,
 domestic_or_overseas TEXT NOT NULL CHECK(domestic_or_overseas IN ('domestic','overseas','mixed','unknown')),
 recipient_country CHAR(2), uk_nation TEXT,
 amount_original NUMERIC(22,2) NOT NULL, original_currency CHAR(3) NOT NULL,
 amount_gbp NUMERIC(22,2), conversion_date DATE,
 source_id BIGINT NOT NULL REFERENCES sources(id),
 source_record_id TEXT, confidence TEXT NOT NULL DEFAULT 'official',
 intergovernmental_transfer BOOLEAN NOT NULL DEFAULT FALSE,
 consolidation_group TEXT, notes TEXT,
 UNIQUE(source_id,source_record_id)
);
CREATE INDEX IF NOT EXISTS records_filter_idx ON records(record_kind, fiscal_year, category);
CREATE INDEX IF NOT EXISTS records_recipient_idx ON records(receiving_entity_id, fiscal_year);
CREATE INDEX IF NOT EXISTS records_overseas_idx ON records(domestic_or_overseas,recipient_country);
CREATE TABLE IF NOT EXISTS record_links (
 parent_record_id BIGINT NOT NULL REFERENCES records(id),
 child_record_id BIGINT NOT NULL REFERENCES records(id),
 relationship TEXT NOT NULL CHECK(relationship IN ('breakdown','same_flow','funded_by','corrects')),
 PRIMARY KEY(parent_record_id,child_record_id,relationship)
);
-- Do not sum aggregates with their constituent transactions.
-- Do not sum intergovernmental transfers twice when consolidating UK spending.
