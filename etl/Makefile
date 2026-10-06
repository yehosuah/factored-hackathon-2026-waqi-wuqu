.PHONY: setup check notebooks test

setup:
	uv sync --locked

check:
	uv lock --check
	uv run --locked ruff check .
	uv run --locked ruff format --check .
	uv run --locked check-environment

notebooks:
	uv sync --locked --group notebooks
	uv run --locked --group notebooks jupyter lab notebooks

test:
	uv run --locked pytest
