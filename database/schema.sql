-- Generated from SQLAlchemy models (src/llm_project/db/models.py, nhs_schema.py).
-- Regenerate after changing models rather than hand-editing.

CREATE TABLE providers (
	provider_code VARCHAR NOT NULL, 
	provider_name VARCHAR NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (provider_code)
);

CREATE TABLE diagnostic_tests (
	test_code VARCHAR NOT NULL, 
	test_name VARCHAR NOT NULL, 
	cdc_alias VARCHAR, 
	PRIMARY KEY (test_code)
);

CREATE TABLE reporting_periods (
	period_id VARCHAR NOT NULL, 
	period_month DATE NOT NULL, 
	period_label VARCHAR NOT NULL, 
	is_complete BOOLEAN NOT NULL, 
	PRIMARY KEY (period_id)
);

CREATE TABLE source_files (
	id SERIAL NOT NULL, 
	dataset VARCHAR NOT NULL, 
	url TEXT NOT NULL, 
	sha256 VARCHAR NOT NULL, 
	downloaded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	reporting_period_id VARCHAR, 
	revision_label VARCHAR, 
	row_count INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_source_files_dataset_hash UNIQUE (dataset, sha256), 
	FOREIGN KEY(reporting_period_id) REFERENCES reporting_periods (period_id)
);

CREATE TABLE diagnostic_waiting_facts (
	id SERIAL NOT NULL, 
	provider_code VARCHAR NOT NULL, 
	test_code VARCHAR NOT NULL, 
	period_id VARCHAR NOT NULL, 
	week_00_01 INTEGER NOT NULL, 
	week_01_02 INTEGER NOT NULL, 
	week_02_03 INTEGER NOT NULL, 
	week_03_04 INTEGER NOT NULL, 
	week_04_05 INTEGER NOT NULL, 
	week_05_06 INTEGER NOT NULL, 
	week_06_07 INTEGER NOT NULL, 
	week_07_08 INTEGER NOT NULL, 
	week_08_09 INTEGER NOT NULL, 
	week_09_10 INTEGER NOT NULL, 
	week_10_11 INTEGER NOT NULL, 
	week_11_12 INTEGER NOT NULL, 
	week_12_13 INTEGER NOT NULL, 
	week_13_plus INTEGER NOT NULL, 
	total_waiting INTEGER NOT NULL, 
	source_file_id INTEGER NOT NULL, 
	source_row_count INTEGER NOT NULL, 
	ingested_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	transformation_version VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_waiting_fact_grain UNIQUE (provider_code, test_code, period_id), 
	CONSTRAINT ck_waiting_total_nonneg CHECK (total_waiting >= 0), 
	FOREIGN KEY(provider_code) REFERENCES providers (provider_code), 
	FOREIGN KEY(test_code) REFERENCES diagnostic_tests (test_code), 
	FOREIGN KEY(period_id) REFERENCES reporting_periods (period_id), 
	FOREIGN KEY(source_file_id) REFERENCES source_files (id)
);

CREATE TABLE diagnostic_activity_facts (
	id SERIAL NOT NULL, 
	provider_code VARCHAR NOT NULL, 
	test_code VARCHAR NOT NULL, 
	period_id VARCHAR NOT NULL, 
	waiting_list_activity INTEGER NOT NULL, 
	planned_activity INTEGER NOT NULL, 
	unscheduled_activity INTEGER NOT NULL, 
	total_activity INTEGER NOT NULL, 
	source_file_id INTEGER NOT NULL, 
	source_row_count INTEGER NOT NULL, 
	ingested_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	transformation_version VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_activity_fact_grain UNIQUE (provider_code, test_code, period_id), 
	CONSTRAINT ck_activity_total_nonneg CHECK (total_activity >= 0), 
	FOREIGN KEY(provider_code) REFERENCES providers (provider_code), 
	FOREIGN KEY(test_code) REFERENCES diagnostic_tests (test_code), 
	FOREIGN KEY(period_id) REFERENCES reporting_periods (period_id), 
	FOREIGN KEY(source_file_id) REFERENCES source_files (id)
);

CREATE TABLE cdc_activity_facts (
	id SERIAL NOT NULL, 
	cdc_code VARCHAR NOT NULL, 
	cdc_name VARCHAR NOT NULL, 
	region_code VARCHAR, 
	region_name VARCHAR, 
	icb VARCHAR, 
	test_code VARCHAR NOT NULL, 
	period_id VARCHAR NOT NULL, 
	provider_code VARCHAR, 
	activity_count INTEGER NOT NULL, 
	source_file_id INTEGER NOT NULL, 
	ingested_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	transformation_version VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_cdc_fact_grain UNIQUE (cdc_code, test_code, period_id), 
	CONSTRAINT ck_cdc_activity_nonneg CHECK (activity_count >= 0), 
	FOREIGN KEY(test_code) REFERENCES diagnostic_tests (test_code), 
	FOREIGN KEY(period_id) REFERENCES reporting_periods (period_id), 
	FOREIGN KEY(provider_code) REFERENCES providers (provider_code), 
	FOREIGN KEY(source_file_id) REFERENCES source_files (id)
);

CREATE TABLE provider_test_month_metrics (
	id SERIAL NOT NULL, 
	provider_code VARCHAR NOT NULL, 
	test_code VARCHAR NOT NULL, 
	period_id VARCHAR NOT NULL, 
	total_waiting INTEGER NOT NULL, 
	waiting_6_plus_weeks INTEGER NOT NULL, 
	percentage_waiting_6_plus_weeks FLOAT NOT NULL, 
	total_activity INTEGER NOT NULL, 
	cdc_activity INTEGER, 
	waiting_list_monthly_change FLOAT, 
	waiting_list_yearly_change FLOAT, 
	activity_monthly_change FLOAT, 
	activity_yearly_change FLOAT, 
	pressure_proxy FLOAT, 
	persistent_pressure_months INTEGER, 
	quality_flag VARCHAR NOT NULL, 
	computed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_metrics_grain UNIQUE (provider_code, test_code, period_id), 
	CONSTRAINT ck_pct_range CHECK (percentage_waiting_6_plus_weeks >= 0 AND percentage_waiting_6_plus_weeks <= 100), 
	FOREIGN KEY(provider_code) REFERENCES providers (provider_code), 
	FOREIGN KEY(test_code) REFERENCES diagnostic_tests (test_code), 
	FOREIGN KEY(period_id) REFERENCES reporting_periods (period_id)
);

CREATE TABLE bottleneck_scores (
	id SERIAL NOT NULL, 
	provider_code VARCHAR NOT NULL, 
	test_code VARCHAR NOT NULL, 
	period_id VARCHAR NOT NULL, 
	weighting_scenario VARCHAR NOT NULL, 
	score FLOAT NOT NULL, 
	component_long_wait FLOAT NOT NULL, 
	component_waiting_growth FLOAT NOT NULL, 
	component_activity_imbalance FLOAT NOT NULL, 
	component_persistence FLOAT NOT NULL, 
	component_cdc_indicator FLOAT NOT NULL, 
	computed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_bottleneck_grain UNIQUE (provider_code, test_code, period_id, weighting_scenario), 
	CONSTRAINT ck_bottleneck_score_range CHECK (score >= 0 AND score <= 100), 
	FOREIGN KEY(provider_code) REFERENCES providers (provider_code), 
	FOREIGN KEY(test_code) REFERENCES diagnostic_tests (test_code), 
	FOREIGN KEY(period_id) REFERENCES reporting_periods (period_id)
);

CREATE TABLE conversations (
	id VARCHAR NOT NULL, 
	question TEXT NOT NULL, 
	search_query TEXT, 
	answer TEXT NOT NULL, 
	mode VARCHAR NOT NULL, 
	retrieval_method VARCHAR, 
	prompt_variant VARCHAR, 
	model VARCHAR NOT NULL, 
	response_time_seconds FLOAT NOT NULL, 
	num_source_docs INTEGER NOT NULL, 
	source_doc_ids TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE feedback (
	id SERIAL NOT NULL, 
	conversation_id VARCHAR NOT NULL, 
	rating INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);
