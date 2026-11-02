# `make verify` is the gate: lint, tests, and the two checkers. It needs the database but
# not the network, and must pass on a clean clone.
#
# `make bench` runs the experiments, which build tables of up to a million rows and take
# a few minutes. A benchmark that runs on every commit stops being run at all.

PYTHON := python3
DSN ?= postgresql://postgres:postgres@127.0.0.1:5433/postgres
export OFFSET_DRIFT_DSN = $(DSN)

.PHONY: help install db-up db-down lint test verify bench tables cli clean

help:
	@echo "make install   install the package and its development dependencies"
	@echo "make db-up     start the PostgreSQL these scans run against"
	@echo "make verify    lint, tests, law check, number check - the gate"
	@echo "make bench     run the three experiments, minutes not seconds"
	@echo "make db-down   stop the database"

install:
	$(PYTHON) -m pip install -e ".[dev]"

db-up:
	docker compose up -d --wait

db-down:
	docker compose down -v

lint:
	$(PYTHON) -m ruff check .

test:
	$(PYTHON) -m pytest

tables:
	$(PYTHON) tools/render_tables.py

# The transcript carries a wall-clock figure, so it lives with the measurements rather
# than in the gate: a verify that dirties the working tree is one people stop reading.
cli:
	$(PYTHON) tools/capture_cli.py

verify: lint test tables
	$(PYTHON) tools/check_laws.py
	$(PYTHON) tools/collect_metrics.py
	$(PYTHON) tools/check_numbers.py

bench: cli
	$(PYTHON) experiments/e1_what_the_scan_misses.py
	$(PYTHON) experiments/e2_the_cost_of_depth.py
	$(PYTHON) experiments/e3_paging_the_whole_table.py

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__ *.egg-info
