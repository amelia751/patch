.DEFAULT_GOAL := help
.PHONY: help sync lint format test verify

help:
	@echo "sync    install the uv workspace (Python 3.12) with dev dependencies"
	@echo "lint    ruff check + format check across the Python trees"
	@echo "format  ruff format (writes)"
	@echo "test    pytest across the workspace"
	@echo "verify  scripts/verify_root.sh — the dynamic root verifier"

sync:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

test:
	uv run pytest -q

verify:
	./scripts/verify_root.sh
