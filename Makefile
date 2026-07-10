.PHONY: check test fmt smoke author-cassettes author-broken-cassettes path-gate path-gate-broken up down record-base replay-base golden-upload golden-verify

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

author-broken-cassettes: ## перегенерить authored subset base-broken-policy ($$0, идемпотентно)
	uv run python -m scripts.author_broken_cassettes

path-gate: ## path-assertion gate по базовой пачке (replay, $$0): таблица ожид vs факт, exit≠0 при регрессии
	AW_CASSETTE_SET=base uv run python -m scripts.path_gate

path-gate-broken: ## демо-регрессия: сломанный policy-check на subset → гейт краснеет (смена маршрута, не cassette-miss)
	AW_CASSETTE_SET=base-broken-policy uv run python -m scripts.path_gate --ids PA-base-001,PA-base-003,PA-base-015,PA-base-019,PA-base-021

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
