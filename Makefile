.PHONY: install lint format typecheck test check secrets

install:
	uv sync --locked

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy

test:
	uv run pytest

# Host gate: everything a PR must pass.
check: lint typecheck test

# Secret scan; needs the gitleaks binary (CI runs it on every push).
secrets:
	gitleaks detect --source . --redact --no-banner
