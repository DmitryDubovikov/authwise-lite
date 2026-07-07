.PHONY: check test fmt smoke author-cassettes up down

check: ## линт + формат + типы + тесты (всё offline, replay)
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy app
	uv run pytest

test:
	uv run pytest

fmt:
	uv run ruff format .
	uv run ruff check --fix .

smoke: ## прогон smoke-фикстуры через граф (replay, $$0), печатает пути
	uv run python -m app.cli fixtures/requests-smoke.jsonl

author-cassettes: ## перегенерить авторские кассеты smoke-набора ($$0, идемпотентно)
	uv run python -m scripts.author_smoke_cassettes

up: ## поднять MLflow (sqlite-бэкенд)
	docker compose up -d mlflow

down:
	docker compose down
