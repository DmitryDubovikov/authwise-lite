.PHONY: check test fmt smoke author-cassettes author-broken-cassettes path-gate path-gate-broken up down obs-up slo-up metrics-push budget-demo slo-verify record-base replay-base trace-base golden-upload golden-verify langfuse-verify record-post replay-post drift-push drift-verify policy-seed policy-swap policy-verify replay-base-champion

# pk-aw/sk-aw — детерминированный dev-сид Langfuse (LANGFUSE_INIT_* в docker-compose.yml), не секрет
LANGFUSE_KEYS = AW_LANGFUSE_PUBLIC_KEY=pk-aw AW_LANGFUSE_SECRET_KEY=sk-aw

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

trace-base: ## replay базовой пачки с трейсингом в Langfuse ($$0; требует obs-up)
	AW_CASSETTE_SET=base $(LANGFUSE_KEYS) uv run python -m app.cli fixtures/requests-base.jsonl

langfuse-verify: ## verify the store (правило 9): per-node спаны + usage/cost запросом к Langfuse API
	$(LANGFUSE_KEYS) uv run python -m scripts.langfuse_verify

golden-upload: ## залить trajectory golden-сет в MLflow Evaluation Dataset (идемпотентно)
	uv run python -m scripts.golden_upload

golden-verify: ## verify в сторе (правило 9): записи + квота singleton из MLflow API
	uv run python -m scripts.golden_verify

record-post: ## записать кассеты «пострелизной» пачки (ДЕНЬГИ ≈$$0.01–0.02, только по явной просьбе — правило 4)
	AW_LLM_MODE=record AW_CASSETTE_SET=post uv run python -m app.cli fixtures/requests-post.jsonl

replay-post: ## прогон «пострелизной» пачки по кассетам (replay, $$0), печатает пути
	AW_CASSETTE_SET=post uv run python -m app.cli fixtures/requests-post.jsonl

drift-push: ## path-drift: доли веток base (reference) vs post (primary) + PSI → Pushgateway; нужны slo-up, replay-base и replay-post
	uv run python -m scripts.drift_push

drift-verify: ## verify the store (правило 9): доли веток и PSI из Prometheus API + alert rule Firing из Grafana API
	uv run python -m scripts.drift_verify

policy-seed: ## routing-policy в MLflow (iter 6): промпты + версии с пинами + alias champion/challenger (идемпотентно; нужен up)
	uv run python -m scripts.policy_seed

policy-swap: ## ручной swap alias champion ↔ challenger на pa-routing-policy (повторный — вернёт исходное)
	uv run python -m scripts.policy_swap

policy-verify: ## verify the store (правило 9): alias, пины и шаблоны routing-policy запросами к MLflow API
	uv run python -m scripts.policy_verify

replay-base-champion: ## alias-загрузка (iter 6): replay базовой пачки с промптами champion из реестра ($$0; нужны up и policy-seed)
	AW_CASSETTE_SET=base AW_ROUTING_POLICY_ALIAS=champion uv run python -m app.cli fixtures/requests-base.jsonl

budget-demo: ## FinOps guardrail: ужатый бюджет рана обрывает retry-loop → escalate [budget] (replay, $$0)
	AW_CASSETTE_SET=base AW_RUN_BUDGET_USD=0.00008 uv run python -m app.cli fixtures/requests-base.jsonl

metrics-push: ## RunRecord базовой пачки → Pushgateway (per-node latency/cost + budget-эскалации); нужны slo-up и replay-base/budget-demo
	AW_CASSETTE_SET=base uv run python -m scripts.metrics_push

slo-verify: ## verify the store (правило 9): per-node серии из Prometheus API + alert rule Firing из Grafana API
	uv run python -m scripts.slo_verify

up: ## поднять MLflow (sqlite-бэкенд)
	docker compose up -d mlflow

obs-up: ## поднять Langfuse-стек (профиль obs); UI http://localhost:3001 (dev@authwise.lite / lite-password)
	docker compose --profile obs up -d

slo-up: ## поднять Prometheus+Pushgateway+Grafana (профиль slo); Grafana http://localhost:3002 (admin / lite-password)
	docker compose --profile slo up -d

down: ## погасить всё, включая obs/slo-профили (трейсы переживают в named volumes; SLO-стек — as-code из slo/)
	docker compose --profile obs --profile slo down
