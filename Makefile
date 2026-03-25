# -----------------------------
# Variables
# -----------------------------
UV = uv
APP = app/main.py

.DEFAULT_GOAL := help

# -----------------------------
# Setup
# -----------------------------

.PHONY: setup
setup: ## Install dependencies (including dev)
	$(UV) sync --extra dev

.PHONY: reset
reset: ## Recreate virtual environment cleanly
	rm -rf .venv
	$(UV) sync --extra dev

.PHONY: lock
lock: ## Update lockfile
	$(UV) lock

# -----------------------------
# Run Application
# -----------------------------

.PHONY: run
run: ## Run the application
	$(UV) run python $(APP)

.PHONY: dev
dev: ## Run with auto-reload (Python files only)
	$(UV) run watchfiles --filter python "python $(APP)"

# -----------------------------
# Code Quality
# -----------------------------

.PHONY: lint
lint: ## Run linter
	$(UV) run ruff check app

.PHONY: lint-fix
lint-fix: ## Fix lint issues
	$(UV) run ruff check --fix app

.PHONY: format
format: ## Format code
	$(UV) run black app

.PHONY: format-check
format-check: ## Check formatting
	$(UV) run black --check app

.PHONY: typecheck
typecheck: ## Run type checking
	$(UV) run mypy app

.PHONY: check
check: lint typecheck ## Run all checks

# -----------------------------
# Testing
# -----------------------------

.PHONY: test
test: ## Run tests
	$(UV) run pytest

# -----------------------------
# Cleanup
# -----------------------------

.PHONY: clean
clean: ## Remove cache files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache

# -----------------------------
# Help
# -----------------------------

.PHONY: help
help:
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## ' Makefile | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'