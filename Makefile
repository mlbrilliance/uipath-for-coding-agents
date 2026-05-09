## AURORA Makefile — common project tasks.
##
## Targets are documented in `make help`. Most are wrappers around uv + aurora CLI
## so contributors don't have to memorize the canonical invocations.

.DEFAULT_GOAL := help
SHELL := /bin/bash

PY := uv run python
PYTEST := uv run pytest

## ---------- Setup ----------

bootstrap:    ## One-shot setup (deps, plugin, validate, tests)
	bash scripts/bootstrap.sh

install:      ## uv sync + uipath skills
	uv sync
	uipath skills install || true

## ---------- Run ----------

start:        ## aurora start — boot the swarm
	uv run aurora start

start-no-daemons: ## aurora start --skip-daemons (in-session only)
	uv run aurora start --skip-daemons

status:       ## aurora status (TUI/JSON)
	uv run aurora status --once --json | jq .

policy:       ## aurora policy validate
	uv run aurora policy validate

policy-strict: ## aurora policy validate --strict
	uv run aurora policy validate --strict

dry-run:      ## aurora policy dry-run
	uv run aurora policy dry-run

## ---------- Demo ----------

demo-break:   ## Inject a failure (invalidates GITHUB_TOKEN, triggers an instance)
	bash examples/oss-supply-chain-defender/break.sh

demo-restore: ## Restore .env from break.sh's backup
	bash examples/oss-supply-chain-defender/restore.sh

## ---------- Quality ----------

test:         ## Run unit tests
	$(PYTEST) tests/unit -v

test-fast:    ## Unit tests, quiet
	$(PYTEST) tests/unit -q --no-header

test-int:     ## Integration tests (requires UIPATH_* env)
	$(PYTEST) tests/integration -v

lint:         ## Ruff
	uv run ruff check lib tests

lint-fix:     ## Ruff with autofix
	uv run ruff check --fix lib tests

typecheck:    ## mypy
	uv run mypy lib

format:       ## Format all Python with ruff
	uv run ruff format lib tests

ci:           ## Run everything CI runs (lint + test + policy validate)
	make lint
	make typecheck
	make policy-strict
	make test

## ---------- Plugin ----------

plugin-install: ## Install AURORA as a Claude Code plugin
	claude plugin marketplace add ./
	claude plugin install aurora@aurora-marketplace

plugin-list:  ## List installed Claude Code plugins
	claude plugin list

## ---------- Cleanup ----------

clean:        ## Remove pycache, build artifacts, virtualenv
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist build *.egg-info
	rm -rf .venv

clean-aurora-state: ## DESTROYS swarm state (memory, fingerprints, learnings)
	@echo "This will delete /opt/aurora/. Continue? [y/N]"
	@read -r yn; if [[ "$$yn" == "y" || "$$yn" == "Y" ]]; then \
		rm -rf /opt/aurora; \
		echo "wiped /opt/aurora"; \
	else \
		echo "aborted"; \
	fi

## ---------- Help ----------

help:         ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  sort | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: help bootstrap install start start-no-daemons status policy policy-strict \
        dry-run demo-break demo-restore test test-fast test-int lint lint-fix \
        typecheck format ci plugin-install plugin-list clean clean-aurora-state
