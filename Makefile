VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
RUFF    := $(VENV)/bin/ruff
MYPY    := $(VENV)/bin/mypy
STREAMLIT := $(VENV)/bin/streamlit

HOST    ?= 127.0.0.1
PORT    ?= 8501

SOURCES := src

.DEFAULT_GOAL := help
.PHONY: help install dev run lint fmt typecheck check clean

help: ## Show this help
	@echo "air-client — make <target>"
	@echo
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "Overridable: HOST=$(HOST) PORT=$(PORT)"

$(PY):
	python3.12 -m venv $(VENV)

install: $(PY) ## Create .venv and install the console
	$(PIP) install --upgrade pip
	$(PIP) install -e .

dev: install ## Add the development toolchain (ruff, mypy)
	$(PIP) install -e ".[dev]"

run: ## Serve the console locally
	$(STREAMLIT) run src/air_client/app.py \
		--server.address $(HOST) --server.port $(PORT)

lint: ## Lint
	$(RUFF) check $(SOURCES)

fmt: ## Format and autofix
	$(RUFF) format $(SOURCES)
	$(RUFF) check --fix $(SOURCES)

typecheck: ## Type-check
	$(MYPY) $(SOURCES)

check: lint typecheck ## Everything CI runs

clean: ## Remove the venv and caches
	rm -rf $(VENV) .ruff_cache .mypy_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
