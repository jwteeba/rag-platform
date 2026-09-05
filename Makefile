.PHONY: install run dev worker test lint format typecheck check pre-commit-install docker-build docker-up docker-down clean db-upgrade db-downgrade db-revision db-current test-db-up test-db-create test-db-migrate test-redis-up test-minio-up test-qdrant-up

install:
	poetry install

# Run the API directly on the host (requires `make install` first, and
# Postgres reachable per APP_DATABASE_URL — see `make db-upgrade`).
run:
	poetry run uvicorn rag_platform.main:app --host 0.0.0.0 --port 8000

# Run with auto-reload for local development.
dev:
	poetry run uvicorn rag_platform.main:app --host 0.0.0.0 --port 8000 --reload

# Run a local Celery worker (Redis and MinIO must be reachable per .env).
# Uses --pool=solo on macOS to avoid SIGABRT from forking after asyncpg/OpenAI
# imports. In production (Linux), the default prefork pool is fine.
worker:
	poetry run celery -A rag_platform.worker.celery worker --loglevel=INFO --pool=solo

# The database/cache/storage `make test` always uses — Docker Compose's
# `postgres`, `redis`, and `minio` services, on their dedicated host ports
# (see the port-mapping comments in docker-compose.yml), never whatever else
# might already be listening on the system defaults. Every `test-*` target
# below and `test` itself pins these explicitly, overriding any
# APP_TEST_* already present in the shell or `.env`.
TEST_DATABASE_URL := postgresql+asyncpg://postgres:postgres@localhost:5433/rag_platform_test
TEST_REDIS_URL := redis://localhost:6380/1
TEST_MINIO_ENDPOINT := localhost:9000
TEST_MINIO_BUCKET := rag-platform-test
TEST_QDRANT_HOST := localhost
TEST_QDRANT_PORT := 6333

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

# Bring an existing test database forward before pytest's per-test cleanup.
# This matters when a developer has kept the Docker volume across migrations.
test-db-migrate: test-db-create
	APP_DATABASE_URL=$(TEST_DATABASE_URL) poetry run alembic upgrade head

# Start (or confirm already running) Docker Compose's redis container, and
# block until it reports healthy.
test-redis-up:
	docker compose up -d redis
	@echo "Waiting for dockerized redis to become healthy..."
	@until docker compose exec -T redis redis-cli ping > /dev/null 2>&1; do sleep 1; done
	@echo "Dockerized redis is healthy."

# Start (or confirm already running) Docker Compose's minio container, block
# until healthy, then ensure the test bucket exists (idempotent).
test-minio-up:
	docker compose up -d minio
	@echo "Waiting for dockerized minio to become healthy..."
	@until docker compose exec -T minio mc ready local > /dev/null 2>&1; do sleep 1; done
	@echo "Dockerized minio is healthy."
	@docker compose exec -T minio mc alias set local http://localhost:9000 minioadmin minioadmin > /dev/null 2>&1 || true
	@docker compose exec -T minio mc mb --ignore-existing local/$(TEST_MINIO_BUCKET) > /dev/null 2>&1 || true

# Start (or confirm already running) Docker Compose's qdrant container, and
# block until it reports healthy.
test-qdrant-up:
	docker compose up -d qdrant
	@echo "Waiting for dockerized qdrant to become healthy..."
	@until docker compose exec -T qdrant python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:6333/healthz')" > /dev/null 2>&1; do sleep 1; done
	@echo "Dockerized qdrant is healthy."

# Runs the suite against Docker Compose's postgres, redis, minio, and qdrant, always —
# regardless of any local install, and regardless of any APP_TEST_* already
# set in your shell or `.env` (the explicit assignment below overrides all of
# them for this command only; nothing is permanently exported to your shell).
test: test-db-migrate test-redis-up test-minio-up test-qdrant-up
	APP_TEST_DATABASE_URL=$(TEST_DATABASE_URL) APP_TEST_REDIS_URL=$(TEST_REDIS_URL) \
	APP_TEST_MINIO_ENDPOINT=$(TEST_MINIO_ENDPOINT) APP_TEST_MINIO_BUCKET=$(TEST_MINIO_BUCKET) \
	APP_TEST_QDRANT_HOST=$(TEST_QDRANT_HOST) APP_TEST_QDRANT_PORT=$(TEST_QDRANT_PORT) \
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
