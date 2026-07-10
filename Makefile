.PHONY: check test fmt smoke author-cassettes up down record-base replay-base golden-upload golden-verify

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

record-base: ## записать кассеты базовой пачки (ДЕНЬГИ ≈$$0.01, только по явной просьбе — правило 4)
	AW_LLM_MODE=record AW_CASSETTE_SET=base uv run python -m app.cli fixtures/requests-base.jsonl

replay-base: ## прогон базовой пачки по кассетам (replay, $$0), печатает пути
	AW_CASSETTE_SET=base uv run python -m app.cli fixtures/requests-base.jsonl

golden-upload: ## залить trajectory golden-сет в MLflow Evaluation Dataset (идемпотентно)
	uv run python -m scripts.golden_upload

golden-verify: ## verify в сторе (правило 9): записи + квота singleton из MLflow API
	uv run python -m scripts.golden_verify

up: ## поднять MLflow (sqlite-бэкенд)
	docker compose up -d mlflow

down:
	docker compose down
