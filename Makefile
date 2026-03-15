# Virtual environment folder
VENV=.venv
PYTHON=$(VENV)/bin/python
PIP=$(VENV)/bin/pip

# Default target
.PHONY: run
run:
	source $(VENV)/bin/activate && python app/main.py

# Create virtual environment
.PHONY: venv
venv:
	python3 -m venv $(VENV)

# Install dependencies
.PHONY: install
install:
	source $(VENV)/bin/activate && pip install -r requirements.txt

# Run the bot using the venv python directly (cleaner)
.PHONY: start
start:
	$(PYTHON) app/main.py

# Run tests
.PHONY: test
test:
	source $(VENV)/bin/activate && pytest

# Format code (optional if you install black)
.PHONY: format
format:
	source $(VENV)/bin/activate && black .

# Clean cache files
.PHONY: clean
clean:
	find . -type d -name "__pycache__" -exec rm -r {} +