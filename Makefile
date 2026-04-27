.RECIPEPREFIX := >
.PHONY: install infra-up migrate format lint typecheck test check run openapi

install:
> pip install -r requirements.txt
> pip install -r requirements-dev.txt

infra-up:
> docker compose up -d db_dev db_test redis_test

migrate:
> python migrations/run_all.py

format:
> ruff format src tests

lint:
> ruff check src tests

typecheck:
> mypy src

test:
> pytest -q

check: format lint typecheck test

run:
> uvicorn src.interfaces.http.app:app --host 0.0.0.0 --port 8000 --reload

openapi:
> python scripts/generate_openapi.py
