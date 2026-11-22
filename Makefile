.DEFAULT_GOAL := help
COMPOSE ?= $(shell docker compose version >/dev/null 2>&1 && printf 'docker compose' || printf 'docker-compose')

.PHONY: help setup dev ui worker test lint typecheck check docker-up docker-down seed eval

help:
	@printf '%s\n' \
		"make setup        Install locked development dependencies" \
		"make dev          Start the development API" \
		"make ui           Start Streamlit" \
		"make worker       Start the ingestion worker" \
		"make test         Run tests with coverage" \
		"make lint         Run Ruff" \
		"make typecheck    Run mypy" \
		"make check        Run all quality gates" \
		"make docker-up    Build and start the full stack" \
		"make docker-down Stop containers without deleting volumes" \
		"make seed         Seed Docker deployment with worker stopped" \
		"make eval         Evaluate local indexes; optional EVAL_ARGS"

setup:
	uv sync --frozen --group dev

dev:
	uv run --frozen uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000

ui:
	uv run --frozen streamlit run src/ui/app.py --server.address 127.0.0.1

worker:
	uv run --frozen celery -A src.tasks.celery_app:celery_app worker --loglevel=info --pool=solo

test:
	uv run --frozen pytest -ra --cov=src --cov-report=term-missing --cov-report=xml

lint:
	uv run --frozen ruff check src tests scripts evaluation

typecheck:
	uv run --frozen mypy src

check: lint typecheck test

docker-up:
	$(COMPOSE) up --build -d

docker-down:
	$(COMPOSE) down

seed:
	$(COMPOSE) stop worker
	@trap '$(COMPOSE) start worker' EXIT; $(COMPOSE) run --rm seed

eval:
	uv run --frozen python -m evaluation.benchmarks.run_benchmark $(EVAL_ARGS)
