.PHONY: help install dev test lint format typecheck run ingest seed build-sandbox smoke check clean

#: Directory holding the extracted Python documentation.
DOCS_SOURCE ?= data/docs-source

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
	python scripts/ingest_docs.py --source $(DOCS_SOURCE)

seed:  ## Seed the vector store with the professor notes
	python scripts/seed_rag.py

build-sandbox:  ## Build the Docker sandbox image
	docker build -t sandbox-evaluador .

smoke:  ## Run the end-to-end smoke test (starts its own server)
	python scripts/smoke_test.py --start-server

check: lint typecheck test  ## Run every quality gate

clean:  ## Remove caches and build artifacts
	@python -c "import pathlib, shutil; dirs = list(pathlib.Path('.').rglob('__pycache__')) + [pathlib.Path(d) for d in ('.pytest_cache', '.ruff_cache', '.mypy_cache')]; [shutil.rmtree(d, ignore_errors=True) for d in dirs]"
