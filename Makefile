.PHONY: install test lint fmt run doctor docker
install:
	python3 -m venv .venv && .venv/bin/pip install -e ".[anthropic,dev]"
test:
	.venv/bin/pytest -q
lint:
	.venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests
fmt:
	.venv/bin/ruff check --fix src tests && .venv/bin/ruff format src tests
run:
	.venv/bin/mars serve
doctor:
	.venv/bin/mars doctor
docker:
	docker compose up --build
