.PHONY: help install dev test lint format typecheck run ingest seed build-sandbox check clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install:  ## Install runtime dependencies
	pip install -r requirements.txt

dev:  ## Install runtime + development dependencies
	pip install -r requirements-dev.txt

test:  ## Run the test suite
	pytest

lint:  ## Run ruff checks
	ruff check .

format:  ## Auto-format and auto-fix
	ruff format .
	ruff check --fix .

typecheck:  ## Run mypy on the application package
	mypy app

run:  ## Start the API server with reload
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

ingest:  ## Ingest the Python documentation into the vector store
	python scripts/ingest_docs.py

seed:  ## Seed the vector store with the professor notes
	python scripts/seed_rag.py

build-sandbox:  ## Build the Docker sandbox image
	docker build -t sandbox-evaluador .

check: lint typecheck test  ## Run every quality gate

clean:  ## Remove caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	ruff clean --force 2>/dev/null || true
