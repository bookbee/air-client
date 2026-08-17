VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
RUFF    := $(VENV)/bin/ruff
MYPY    := $(VENV)/bin/mypy
STREAMLIT := $(VENV)/bin/streamlit

HOST    ?= 127.0.0.1
PORT    ?= 8501
# Force an appearance for the whole session, Streamlit's chrome included:
# `make run THEME=dark`. Unset means follow the operating system.
THEME   ?=
THEME_FLAG := $(if $(THEME),--theme.base $(THEME),)
# Auto-rerun on save is on in .streamlit/config.toml, so that every launch path
# behaves the same. Set RELOAD=false to override it for one run.
RELOAD  ?=
RELOAD_FLAG := $(if $(RELOAD),--server.runOnSave $(RELOAD),)
LOG     ?= .run/console.log

COMPOSE ?= docker compose
IMAGE   ?= air-client
TAG     ?= dev

# The listening server, and only it. `lsof -ti tcp:$(PORT)` on its own also
# matches every client *connected* to that port — including the browser tab you
# have the console open in, which `make stop` would then kill.
LISTENER = lsof -ti tcp:$(PORT) -sTCP:LISTEN 2>/dev/null

SOURCES := src

.DEFAULT_GOAL := help
.PHONY: help install dev env run start stop restart status logs image up down lint fmt typecheck check clean

help: ## Show this help
	@echo "air-client — make <target>"
	@echo
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "Overridable: HOST=$(HOST) PORT=$(PORT) THEME=$(THEME) RELOAD=$(RELOAD)"

$(PY):
	python3.12 -m venv $(VENV)

install: $(PY) ## Create .venv and install the console
	$(PIP) install --upgrade pip
	$(PIP) install -e .

dev: install ## Add the development toolchain (ruff, mypy)
	$(PIP) install -e ".[dev]"

env: ## Create .env from .env.example if it does not exist yet
	@test -f .env && echo ".env exists — leaving it alone." \
		|| { cp .env.example .env; echo ".env created. Add your remote targets to it."; }

run: env ## Serve in this terminal; Ctrl+C stops it (THEME=light|dark to force appearance)
	$(STREAMLIT) run src/air_client/app.py \
		--server.address $(HOST) --server.port $(PORT) \
		$(RELOAD_FLAG) $(THEME_FLAG)

start: env ## Serve in the background, logging to .run/console.log
	@if [ -n "$$($(LISTENER))" ]; then \
		echo "already serving on :$(PORT) — 'make restart' to replace it"; exit 1; fi
	@mkdir -p $(dir $(LOG))
	@nohup $(STREAMLIT) run src/air_client/app.py \
		--server.address $(HOST) --server.port $(PORT) \
		$(RELOAD_FLAG) $(THEME_FLAG) > $(LOG) 2>&1 & \
		sleep 2; echo "serving http://$(HOST):$(PORT) · logs: $(LOG)"

stop: ## Stop the console (whatever is serving on PORT)
	@pid=$$($(LISTENER) | xargs); \
	if [ -z "$$pid" ]; then echo "nothing serving on :$(PORT)"; else \
		kill $$pid 2>/dev/null; sleep 1; \
		if kill -0 $$pid 2>/dev/null; then kill -9 $$pid 2>/dev/null; fi; \
		echo "stopped :$(PORT) (pid $$pid)"; fi

restart: stop start ## Stop it and start again in the background

status: ## Say whether the console is serving, and where
	@pid=$$($(LISTENER) | xargs); \
	if [ -z "$$pid" ]; then echo "not serving on :$(PORT)"; else \
		echo "serving http://$(HOST):$(PORT) (pid $$pid)"; fi

logs: ## Tail the container logs (local run logs to .run/console.log)
	$(COMPOSE) logs -f --tail=100 air-client

image: ## Build the runtime image
	docker build -t $(IMAGE):$(TAG) .

up: ## Run the console in Docker (targets the Docker host, not the container)
	@if [ -n "$$($(LISTENER))" ]; then \
		echo "port $(PORT) is taken by a local run — 'make stop' first"; exit 1; fi
	$(COMPOSE) up -d --build
	@echo "serving http://$(HOST):$(PORT) · '$(COMPOSE) logs -f' to follow"

down: ## Stop the Docker console
	$(COMPOSE) down --remove-orphans

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
