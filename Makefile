# gulf-health-lakehouse — task runner.
# Targets grow as phases land. Use a venv: python -m venv .venv && source .venv/bin/activate
.DEFAULT_GOAL := help
PY ?= python

.PHONY: help install generate generate-small test lint clean

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

lint: ## Ruff lint
	$(PY) -m ruff check .

clean: ## Remove generated data + caches (keeps committed sample)
	rm -rf data/raw/*.parquet data/raw/*.csv .pytest_cache **/__pycache__
