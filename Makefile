.PHONY: install run dev test lint format typecheck check pre-commit-install docker-build docker-up docker-down clean

install:
	poetry install

# Run the API directly on the host (requires `make install` first).
run:
	poetry run uvicorn rag_platform.main:app --host 0.0.0.0 --port 8000

# Run with auto-reload for local development.
dev:
	poetry run uvicorn rag_platform.main:app --host 0.0.0.0 --port 8000 --reload

test:
	poetry run pytest

lint:
	poetry run ruff check .

format:
	poetry run black .
	poetry run ruff check --fix .

typecheck:
	poetry run mypy src

# Everything CI runs, in one command.
check: lint typecheck test

pre-commit-install:
	poetry run pre-commit install

docker-build:
	docker compose build

docker-up:
	docker compose up --build

docker-down:
	docker compose down -v

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml .coverage
