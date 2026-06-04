.PHONY: install dev test test-pg lint format init-db seed-demo evaluate download inspect transform synth load ingest docker-up docker-down docker-ingest clean

install:
	pip install --upgrade pip && pip install -r requirements.txt

dev:
	uvicorn app.main:app --reload --port 8000

test:
	pytest

# Run the suite (incl. pgvector integration tests) against a local Postgres.
# Requires a running pgvector Postgres; override DATABASE_URL as needed.
test-pg:
	DATABASE_URL="postgresql+psycopg2://dealflow:dealflow@localhost:5432/dealflow" pytest -q

lint:
	ruff check app scripts tests

# Run agent evaluation checks against the currently-loaded data.
evaluate:
	python -m scripts.evaluate_agent

format:
	ruff format app scripts tests
	ruff check --fix app scripts tests

init-db:
	python -m app.db.init_db

# Fully offline demo dataset (no Kaggle needed).
seed-demo:
	python -m scripts.seed_demo_data

# --- Real ingestion pipeline (requires Kaggle credentials) ---
download:
	python -m scripts.download_datasets

inspect:
	python -m scripts.inspect_datasets

transform:
	python -m scripts.transform_datasets

synth:
	python -m scripts.generate_synthetic_layer

load:
	python -m scripts.load_postgres

ingest: download transform synth load
	@echo "Ingestion complete."

# --- Docker ---
docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

# Run the offline seed inside the API container (after docker-up).
docker-ingest:
	docker compose exec api python -m scripts.seed_demo_data

clean:
	rm -f dealflow.db
	rm -rf data/processed/*.csv
