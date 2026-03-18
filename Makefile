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
setup: ## Install dependencies including dev tools
	$(UV) sync --extra dev

.PHONY: lock
lock: ## Update dependency lockfile
	$(UV) lock

# -----------------------------
# Run Application
# -----------------------------

.PHONY: run
run: ## Run the application
	$(UV) run python $(APP)

.PHONY: dev
dev: ## Run bot with auto-reload
	$(UV) run watchfiles python $(APP)

# -----------------------------
# Code Quality
# -----------------------------

.PHONY: lint
lint: ## Run linter
	$(UV) run ruff check --fix app

.PHONY: lint-fix
lint-fix: ## Auto-fix lint issues
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
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache

# -----------------------------
# Help
# -----------------------------

.PHONY: help
help:
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## ' Makefile | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'