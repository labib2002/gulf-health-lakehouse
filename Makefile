# gulf-health-lakehouse — task runner.
# Targets grow as phases land. Use a venv: python -m venv .venv && source .venv/bin/activate
.DEFAULT_GOAL := help
PY ?= python

.PHONY: help install generate generate-small test lint clean up down build load db-shell

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install runtime + dev deps into the active environment
	$(PY) -m pip install -e ".[dev]"

generate: ## Generate the FULL synthetic dataset to data/raw/ (+ sample)
	$(PY) -m data_generator.generate

generate-small: ## Generate a tiny dataset (fast smoke; no sample overwrite)
	$(PY) -m data_generator.generate --users 20 --months 3 --no-sample

test: ## Run pytest
	$(PY) -m pytest

ab-test: ## Run the A/B analysis (needs full generated data: make generate)
	$(PY) -m analysis.ab_test.ab_test

lint: ## Ruff lint
	$(PY) -m ruff check .

clean: ## Remove generated data + caches (keeps committed sample)
	rm -rf data/raw/*.parquet data/raw/*.csv .pytest_cache **/__pycache__

# --- dbt (Phase 3) ---
DBT := cd transform/dbt && DBT_PROFILES_DIR=$$PWD POSTGRES_HOST=localhost $(PY) -m dbt.cli.main

dbt-deps: ## Install dbt packages (dbt_utils)
	$(DBT) deps

dbt: ## Run dbt build (models + tests) against the loaded Postgres
	$(DBT) build

dbt-docs: ## Generate + serve the dbt lineage docs
	$(DBT) docs generate && $(DBT) docs serve

# --- Docker (Phase 1) ---
build: ## Build the runner image
	docker compose build runner

up: ## Start Postgres (detached) and wait for healthy
	docker compose up -d postgres

down: ## Stop the stack (keeps the pgdata volume)
	docker compose down

load: ## Generate (in container) then load into Postgres
	docker compose run --rm runner -m data_generator.generate
	docker compose run --rm runner -m ingestion.load_to_postgres

db-shell: ## psql into the running Postgres
	docker exec -it ghl-postgres psql -U $${POSTGRES_USER:-health} -d $${POSTGRES_DB:-health}
