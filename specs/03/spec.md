# Итерация 03 — Per-node cost/latency attribution (Langfuse)

> 🎯 Новая техника на старом стеке, минимальными затратами. Existence-gate, не accuracy-gate.

## Цель
Ввести **атрибуцию cost/latency к ноде графа** (graph-level LLM FinOps: измерение): каждый
запуск заявки — трейс в Langfuse, где спан каждой ноды и generation LLM-вызова с usage/cost
привязаны к конкретной ноде, а не к рану целиком. Всё в replay, $0.

## 🧵 Красная нить (резюме)
Дословно из ROADMAP (строка iter 3): **«Per-node cost/latency attribution (graph-level LLM
FinOps: измерение)»** — спаны атрибутируются **по ноде графа**, не по всему run; Langfuse
подключён через **LangGraph-интеграцию (callback handler)** — она включает Agent Graph-вид,
голый OTel его не даёт; Langfuse добавлен в Compose; дашборд бьёт cost/latency по нодам и
называет просевшую ноду.

## Новая техника (и минимальный объём)
- **Langfuse через LangGraph CallbackHandler** (каркас policywise — там был голый OTLP; здесь
  handler ради Agent Graph): handler передаётся в `config={"callbacks": [...]}` на boundary
  раннера → корень трейса + спан на каждую ноду. Трейсинг включается только при заданных
  `AW_LANGFUSE_*`-ключах; выключен (дефолт, тесты, CI) — чистый no-op, сервер не нужен.
- **Generation-шов в `route()`** (решение 2026-07-10, отложенная деталь «уживание с OTel»):
  `app/llm/tracing.py` — no-op контекст-менеджер, когда трейсинг выключен; `route()`
  оборачивает вызов generation-спаном (OTel-контекст сам вложит его под спан ноды). Usage — из
  ответа/кассеты, **cost — только наша domain-функция** (решение 2026-07-10): явный
  `cost_details`, автоинференс цен Langfuse не используем — один прайс-лист `llm-tiers.yaml`.
- **`cost_usd()` в domain** (контракт №5): чистая функция usage × цены тира; цены уже в
  `llm-tiers.yaml`. Потребители: tracing (здесь), Prometheus/SLO (iter 4).
- **`RunRecord` + per-node usage/latency** (контракт №3, отложено из iter 2): `route()` меряет
  латентность вызова, ноды собирают `{node, attempt, usage, latency_ms}` в стейт →
  `RunRecord`/JSONL. Prometheus (iter 4) и Phoenix (iter 5) читают его. `PathTrace` не трогаем.

## Done-gate (по факту существования)
- Compose-профиль `obs` (перенос policywise): langfuse-web/worker + свои pg/clickhouse/redis/
  minio; ключи детерминированы через `LANGFUSE_INIT_*`; host-порт только у UI (3001 — 3000
  занят policywise). `make obs-up` поднимает; MLflow-стек не тяжелеет.
- Прогон базовой пачки в replay (`make replay-base` с ключами) даёт трейсы: спан на ноду,
  внутри LLM-нод — generation с моделью, usage и нашим cost; Agent Graph-вид открывается.
- **Verify the store (правило 9):** скрипт по Langfuse public API — в свежем трейсе спаны
  названы нодами графа и generation несёт usage+cost; не скрин UI.
- Дашборд Langfuse (cost/latency по именам observation) собран и называет просевшую ноду
  (policy-check — retry-циклы дороже); кадр — материал витрины.
- `RunRecord` JSONL содержит per-node usage/latency; `make check` зелёный без Langfuse-сервера.
- Ревью-пайплайн чист (CRITICAL/BUG = 0).

*Идемпотентность:* реестр (MLflow) не мутируется; трейсы — append-only лог наблюдаемости,
повторный прогон = новые трейсы, alias/версии не дрейфуют.

## Шаги
1. `app/domain/cost.py`: `cost_usd(usage, prices)` (контракт №5) + парсинг цен в `llm/tiers.py`.
2. Контракт №3: `LLMReply.latency_ms` (меряет `route()`), `node_stats` в стейте графа →
   `PARunResult`/`RunRecord`/JSONL; потребители не ломаются.
3. `app/llm/tracing.py` (клиент из `Settings`, lazy import, no-op без ключей; generation-шов в
   `route()`; фабрика handler'а) + wiring в `run_pa_request`; пин `langfuse>=3,<4`.
4. Compose `obs`-профиль + `make obs-up`/`obs-down`; `scripts/langfuse_verify.py` (правило 9).
5. Ревью-пайплайн (general + constitution → auditor → фиксы → `/simplify`).

## Вне scope
- Prometheus/Grafana, SLO-алерты, budget controls (iter 4); Phoenix/дрейф (iter 5); реестр
  промптов (iter 6). Никаких live/record-прогонов — только replay, $0.
- Новые ветки/ноды/поля `PathTrace` (заморожен); OTel-спаны не источник истины ассертов
  (правило 6) — golden/CI живут на `PathTrace`, трейсинг в CI выключен.
- Прайс-таблица моделей в Langfuse UI (второй источник цен); LiteLLM-callbacks (правило 5).
