.PHONY: install run dev test lint format typecheck check pre-commit-install docker-build docker-up docker-down clean db-upgrade db-downgrade db-revision db-current test-db-up test-db-create

install:
	poetry install

# Run the API directly on the host (requires `make install` first, and
# Postgres reachable per APP_DATABASE_URL — see `make db-upgrade`).
run:
	poetry run uvicorn rag_platform.main:app --host 0.0.0.0 --port 8000

# Run with auto-reload for local development.
dev:
	poetry run uvicorn rag_platform.main:app --host 0.0.0.0 --port 8000 --reload

# The database `make test` always uses — Docker Compose's `postgres`
# service, on its dedicated host port (see the port-mapping comment in
# docker-compose.yml), never whatever else might be listening on the
# system default 5432. Every `test-*` target below and `test` itself pins
# this explicitly, overriding any `APP_TEST_DATABASE_URL` already present
# in the shell or `.env` — `make test` must be reproducible regardless of
# what else is installed on a given machine.
TEST_DATABASE_URL := postgresql+asyncpg://postgres:postgres@localhost:5433/rag_platform_test

# Start (or confirm already running) Docker Compose's postgres container,
# and block until it reports healthy. `-T` on the exec below disables
# pseudo-tty allocation, required for this to work non-interactively (CI,
# scripts) rather than only in an interactive terminal.
test-db-up:
	docker compose up -d postgres
	@echo "Waiting for dockerized postgres to become healthy..."
	@until docker compose exec -T postgres pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
	@echo "Dockerized postgres is healthy."

# Ensure the dedicated test database exists inside the container.
# Idempotent: safe to run every time, does nothing if it's already there.
test-db-create: test-db-up
	@docker compose exec -T postgres psql -U postgres -tc \
		"SELECT 1 FROM pg_database WHERE datname = 'rag_platform_test'" | grep -q 1 || \
		docker compose exec -T postgres createdb -U postgres rag_platform_test

# Runs the suite against Docker Compose's postgres, always — regardless of
# any local Postgres install, and regardless of any APP_TEST_DATABASE_URL
# or APP_DATABASE_URL already set in your shell or `.env` (the explicit
# assignment below overrides both for this command only; nothing is
# permanently exported to your shell).
test: test-db-create
	APP_TEST_DATABASE_URL=$(TEST_DATABASE_URL) poetry run pytest

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

# Apply all pending migrations. Run this after `make docker-up` / whenever
# Postgres is first reachable, and after pulling any new migration file.
db-upgrade:
	poetry run alembic upgrade head

# Roll back the most recent migration.
db-downgrade:
	poetry run alembic downgrade -1

# Autogenerate a new migration from model changes. Always review the
# generated file before committing it — autogenerate is a starting point,
# not a guarantee.
db-revision:
	poetry run alembic revision --autogenerate -m "$(m)"

db-current:
	poetry run alembic current

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml .coverage
