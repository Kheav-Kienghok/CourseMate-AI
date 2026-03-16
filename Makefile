# Variables
VENV = .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip
APP = app/main.py

# Default target
.DEFAULT_GOAL := help

# -----------------------------
# Setup
# -----------------------------

.PHONY: setup
setup: venv install ## Create venv and install dependencies

.PHONY: venv
venv: ## Create virtual environment
	python3 -m venv $(VENV)

.PHONY: install
install: ## Install dependencies
	$(PIP) install -r requirements.txt

# -----------------------------
# Run Application
# -----------------------------

.PHONY: run
run: ## Run the application
	$(PYTHON) $(APP)

.PHONY: dev
dev: ## Run bot in development mode
	$(PYTHON) $(APP)

# -----------------------------
# Code Quality
# -----------------------------

.PHONY: lint
lint: ## Run linter
	$(PYTHON) -m flake8 app

.PHONY: format
format: ## Format code with black
	$(PYTHON) -m black --target-version py312 app

# -----------------------------
# Cleanup
# -----------------------------

.PHONY: clean
clean: ## Remove cache files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# -----------------------------
# Help
# -----------------------------

.PHONY: help
help:
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## ' Makefile | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'
