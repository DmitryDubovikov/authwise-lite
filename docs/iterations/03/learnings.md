# Learnings — итерация 03

## Ключевые решения и почему

- **Langfuse через LangGraph `CallbackHandler`, а не голый OTLP (как в policywise).** Причина —
  north-star-кадр витрины: только handler включает Langfuse **Agent Graph**-вид (граф с реально
  пройденным маршрутом). Голый OTel даёт плоский список спанов, структуру графа не восстанавливает
  (ROADMAP, решение iter 3). Handler передаётся в `config={"callbacks": [...]}` на boundary
  раннера — он сам заводит корень трейса и спан на каждую ноду.

- **generation-спан создаёт сам `route()`, а не handler.** Отложенная из планирования деталь
  «уживание с OTel вокруг `route()`» (решение 2026-07-10). Handler видит ноды графа, но LLM-вызов
  спрятан внутри нашего единственного шва `route()` (LiteLLM), куда handler не дотягивается. Поэтому
  generation заводит `tracing.generation(node, tier)` прямо в `route()`; OTel-контекст Langfuse v3
  автоматически вкладывает его **под спан текущей ноды** — так и получается атрибуция generation→нода.
  Это НЕ callback LiteLLM (правило 5: LiteLLM остаётся без callbacks) — это отдельный шов Langfuse.

- **Cost считает наша `cost_usd`, автоинференс цен Langfuse выключен.** Решение 2026-07-10: цену
  пишем явным `cost_details` из `llm-tiers.yaml`, а не отдаём Langfuse считать по её собственной
  таблице моделей. Один источник цен на весь проект (контракт №5); ту же функцию в iter 4 использует
  Prometheus/SLO. Резюме-строка «per-node cost» остаётся честной — число из нашего прайс-листа.

- **Трейсинг включается только при ОБОИХ ключах; иначе чистый no-op с lazy-import.** Тот же приём,
  что lazy-import LiteLLM в replay (правило 5): выключенная фича не тянет свой SDK. `enabled()` =
  оба `AW_LANGFUSE_*` заданы; `from langfuse import ...` спрятан внутрь функций `tracing.py`. Это
  держит `make check`/CI офлайн и бесплатным, а `test_disabled_tracing_does_not_import_langfuse`
  стережёт, что полный replay-прогон графа не затягивает `langfuse` в `sys.modules`.

- **`node_stats` рядом с `PathTrace`, а не внутри него.** `PathTrace` заморожен (правило 3) — новых
  полей не добавляем. Per-node usage/latency живут отдельным полем `RunRecord.node_stats` (контракт
  №3, отложенный из iter 2). Источник истины путей — по-прежнему `PathTrace` (правило 6); `node_stats`
  — наблюдаемость, в golden/CI не ассертится. Именно этот артефакт в iter 4/5 читают Prometheus и
  Phoenix.

- **`resolve_model` → `resolve_tier`.** Раньше потребителю нужна была только строка модели; теперь
  шов `route()` берёт из тира и цены (`input_per_1m`/`output_per_1m`), поэтому резолвер отдаёт весь
  `Tier`, а не `.model`. Точки вызова в скриптах-авторах кассет переписаны на `.model` явно.

## Грабли

- **`ENCRYPTION_KEY` из одних нулей YAML парсит как число.** В docker-compose без кавычек строка
  `0000…0` (64 нуля) читается как integer `0`, и Langfuse падает «ENCRYPTION_KEY must be 256 bits /
  64 hex». Лечится кавычками (`"0000…"`). Отмечено комментарием прямо в compose.

- **Healthcheck-асимметрия Langfuse-стека.** langfuse-web/worker сами ретраят коннект к своим
  pg/clickhouse, поэтому те заведены как `service_started`; а redis/minio ждём готовыми по их
  healthcheck (`service_healthy`) + одноразовый `langfuse-minio-init` создаёт бакет
  (`service_completed_successfully`). Иначе worker стартует раньше, чем есть куда лить события.

- **Ингест трейсов асинхронный.** `tracing.flush()` на границе пачки дожимает батч SDK, но
  Langfuse-worker кладёт трейс в ClickHouse не мгновенно — public API `/traces` может секунду-две
  не видеть свежий трейс. В `demo.md` шаг verify снабжён оговоркой «подожди 2–3 с и повтори», сам
  скрипт при пустом ответе даёт внятный `SystemExit`, а не падает стеком.

- **Порт 3001, не 3000.** 3000 занят Langfuse сиблинга policywise-lite (как и 5051 у MLflow против
  5050 triagewise). Зафиксировано в `Settings.langfuse_host` и в маппинге порта compose.

## Осознанные срезы и отложенные TODO

- **SLO/алерты — НЕ здесь (iter 4).** iter 3 — только *измерение* по нодам (attribution). Пороги,
  alert rule, Grafana-дашборд — скоуп iter 4 (Prometheus/Grafana, единственный новый инструмент
  проекта). Перекрытие с Langfuse осознанное: Langfuse = трейсинг/атрибуция, Prom/Grafana =
  SLO/алертинг.

- **Латентность в replay ≈ 0.** Кассеты читаются с диска за микросекунды — `latency_ms` в JSONL
  сотые доли мс. Осмысленные абсолютные задержки — при live-прогонах; для existence-gate достаточно,
  что поле есть и привязано к ноде. Демо SLO-алерта в iter 4 обойдёт это ужатым порогом (ROADMAP
  Заметки №4).

- **Трейсинг в CI выключен намеренно.** OTel-спаны — не источник истины ассертов (правило 6);
  golden/CI живут на `PathTrace`. Поэтому CI гоняет всё без ключей `AW_LANGFUSE_*` — трейсинг no-op,
  сервер в CI не нужен.

- **`langfuse_verify` проверяет один свежий трейс, не всю пачку.** Для existence-gate достаточно:
  доказываем, что атрибуция по нодам *существует и корректна* в реальном трейсе (спаны=ноды,
  generation вложен в свою ноду, usage+cost есть). Полный аудит всех 30 трейсов — избыточен для
  ворот по факту существования (правило 1).
