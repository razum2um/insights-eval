# insights-eval — audit-field honesty eval for the insights MCP server.

INSIGHTS_REPO ?= $(HOME)/src/insights
MODEL         ?= anthropic/claude-sonnet-4-6
export INSIGHTS_REPO

.PHONY: help setup seed lint test check eval eval-quick view clean

help:
	@echo "make setup   - uv sync this project (and a reminder for the insights repo)"
	@echo "make seed    - create + seed the local Postgres DB the MCP server reads"
	@echo "make lint    - ruff check + format check"
	@echo "make test    - run the unit tests (no API key, no DB needed)"
	@echo "make check   - lint + test (what CI runs)"
	@echo "make eval    - run the full eval   (MODEL=$(MODEL))"
	@echo "make eval-quick - run 3 samples as a smoke test"
	@echo "make view    - open the Inspect log viewer"

setup:
	uv sync
	@echo "Also ensure the insights repo is synced: (cd $(INSIGHTS_REPO) && uv sync)"

seed:
	uv run python scripts/seed_eval_db.py

lint:
	uv run ruff check .
	uv run ruff format --check .

test:
	uv run pytest -q

check: lint test

eval:
	uv run inspect eval insights_eval/task.py --model $(MODEL)

eval-quick:
	uv run inspect eval insights_eval/task.py --model $(MODEL) --limit 3

view:
	uv run inspect view

clean:
	rm -rf logs/*.eval .pytest_cache
