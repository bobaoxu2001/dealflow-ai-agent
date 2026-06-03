.PHONY: install dev test lint format init-db seed-demo download inspect transform synth load ingest docker-up docker-down docker-ingest clean

install:
	pip install --upgrade pip && pip install -r requirements.txt

dev:
	uvicorn app.main:app --reload --port 8000

test:
	pytest

lint:
	ruff check app scripts tests

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
