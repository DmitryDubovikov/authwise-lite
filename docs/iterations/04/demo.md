# Демо итерации 04 — Agent FinOps guardrails (per-node SLO alerting + runtime budget controls)

Прогон доказывает **два FinOps-предохранителя** над путём агента (пункты 4 и 5 north-star).
Ценность за пределами демо: агент перестаёт быть «настроили и молимся» — у каждого рана есть потолок
расходов, а просадка ноды сама поднимает руку. Демо показывает по очереди: (1) `make check`/CI
остаются офлайн — SLO-стек им не нужен; (2) **budget control** — под ужатым бюджетом retry-loop
обрывается в `escalate  [budget]`, то есть исчерпание бюджета видно **как маршрут** в траектории;
(3) с дефолтным бюджетом golden-пути не меняются — `path-gate` зелёный; (4) per-node latency/cost и
счётчик budget-эскалаций уходят в Prometheus, а Grafana поднимает **alert rule, называющий просевшую
ноду**; (5) сам стор это подтверждает запросом к API (правило 9), а повторный push идемпотентен.

Все команды выполняются из корня репо: `/Users/dd/projects/pet/authwise-lite` (бинарь `uv` —
`/Users/dd/.local/bin/uv`). Вся итерация **бесплатная** — LLM не зовётся, всё в replay ($0).
Live-шагов нет.

## 1. Окружение

Зачем: остальные шаги гоняются через `uv run` из локального venv; iter 4 добавила зависимость
`prometheus-client` (клиент для push в Pushgateway).

```bash
uv sync --extra dev
```

**Ожидаемо:** завершается без ошибок; в выводе — установка `prometheus-client` (venv `.venv/`
обновлён из `uv.lock`).

## 2. Статический гейт (то, что гоняет CI) — SLO-стек здесь НЕ нужен

Зачем: `make check` — ровно то, что гоняет CI, и оно должно оставаться офлайн и бесплатным. Ни
Prometheus, ни Grafana для него не поднимаются; бюджетные тесты гоняются целиком в replay.

```bash
make check
```

**Ожидаемо:** все шаги зелёные (ruff check, ruff format, mypy, pytest), последняя строка pytest —
`56 passed`. Никакого docker/сети не требуется.

## 3. Точечные тесты техники iter 4

Зачем: сузить до тестов именно этой итерации — бюджетный гейт `decide`, budget-эскалация как
маршрут в графе/`RunRecord`, per-node агрегаты для Prometheus.

```bash
uv run pytest tests/test_budget.py tests/test_metrics.py \
  tests/test_domain.py -k "decide" -v
```

**Ожидаемо:** все `passed` (в т.ч. `test_squeezed_budget_turns_retry_loop_into_escalate` —
ужатый бюджет обрывает второй retry в `escalate`; `test_decide_exhausted_budget_escalates_instead_of_retry`
— контракт №2: исчерпание бюджета — маршрут, не исключение; `test_decide_budget_gates_only_retry`
— бюджет не трогает approve/out_of_policy; `test_aggregate_batch_per_node` — свёртка cost/latency
по нодам).

## 4. Budget control в действии — retry-loop обрывается в `escalate` (кадр витрины)

Зачем: это и есть техника «runtime budget controls» — исчерпание бюджета становится **маршрутом**,
видимым в траектории, а не исключением. `make budget-demo` = обычный replay базовой пачки, но с
ужатым бюджетом `AW_RUN_BUDGET_USD=0.00008` через env: его хватает на первый retry, но не на второй.
Полный прогон пишет `RunRecord` в `runs/base.jsonl` (его прочитает шаг 7).

```bash
make budget-demo
```

**Ожидаемо:** 30 строк путей; у retry-тяжёлых заявок retry-loop обрывается маркером `[budget]`:

```
PA-base-019: classify → policy-check → request-info ↻1 → escalate  [budget]
PA-base-020: classify → policy-check → request-info ↻1 → escalate  [budget]
PA-base-025: classify → policy-check → request-info ↻1 → escalate  [budget]
PA-base-026: classify → policy-check → request-info ↻1 → escalate  [budget]
```

Именно **сам путь** (`… → request-info ↻1 → escalate  [budget]`) и есть артефакт: заявка `PA-base-019`,
чей golden-путь `request-info ↻2`, под ужатым бюджетом сворачивает к человеку после первого цикла.
Всего 4 заявки уходят в budget-escalate.

## 5. Дефолтный бюджет golden-пути НЕ меняет — path-gate зелёный

Зачем: guardrail не должен ломать штатные маршруты. Дефолтный бюджет `$0.05` — с ~350× запасом над
самым дорогим golden-раном, поэтому по базовой пачке path-gate обязан остаться зелёным (регрессии
маршрутизации нет).

```bash
AW_CASSETTE_SET=base uv run python -m scripts.path_gate | tail -3
```

**Ожидаемо:** последние строки — `────…`, `PASS`, exit-код `0`. Все 30 заявок совпали с golden
(`PA-base-019` снова `request-info ↻2` — под дефолтным бюджетом retry-loop доходит до потолка N).
Замечание: этот шаг перезаписывает `runs/base.jsonl` дефолтным прогоном (0 эскалаций) — поэтому
шаг 7 гоним после повторного `make budget-demo`, чтобы счётчик эскалаций в Prometheus был ненулевым.

## 6. Поднять SLO-стек (профиль `slo`)

Зачем: per-node SLO показываем в Prometheus + Grafana — их нужно поднять. Профиль `slo` держит стек
отдельно от лёгкого `make up` (MLflow): поднимаются prometheus + pushgateway + grafana, все
провижинятся as-code из `slo/` (named volume нет — состояние воспроизводимо из репо).

```bash
make slo-up
docker compose --profile slo ps
```

**Ожидаемо:** поднимаются `prometheus`, `pushgateway`, `grafana`; `ps` показывает их `Up` с портами
`0.0.0.0:9090->9090`, `0.0.0.0:9091->9091`, `0.0.0.0:3002->3000`. UI Grafana (для витрины, не для
доказательства): http://localhost:3002 — вход `admin` / `lite-password`.

## 7. Push per-node метрик в Prometheus — $0, из RunRecord (не гоняя граф)

Зачем: это техника «per-node метрики → Prometheus». Сначала перегоняем budget-demo (чтобы в
`runs/base.jsonl` были budget-эскалации после шага 5), затем `make metrics-push` читает этот
`RunRecord`, сворачивает per-node агрегаты и пушит их gauge'ами в Pushgateway. Граф заново **не
гоняется** (контракт №3), cost — из usage кассет через `cost_usd` (контракт №5).

```bash
make budget-demo >/dev/null && make metrics-push
```

**Ожидаемо:** по строке на LLM-ноду и итог, например:

```
classify: calls=30 latency_avg=0.023ms cost=$0.000546
policy-check: calls=39 latency_avg=0.026ms cost=$0.001463
runs=30 budget_escalations=4
→ pushed в http://localhost:9091 (job=authwise-batch, set=base)
```

Числа `calls`/`cost`/`budget_escalations` детерминированы (usage из кассет; `policy-check` дёргается
39 раз = 30 первых проходов + 9 retry-циклов); `latency_avg` — сотые доли мс (replay читает кассету
с диска), значение слегка плавает от прогона к прогону.

## 8. Verify the store (правило 9) — per-node серии + alert Firing, запросом к API

Зачем: доказываем **из стора, а не из UI**. `make slo-verify` спрашивает Prometheus HTTP API
(per-node latency/cost-серии и счётчик эскалаций реально скрейпятся) и Grafana API (alert rule
существует и в состоянии Firing — демо-порог ужат, латентность replay его пробивает). Grafana
считает правило каждые 10 с и требует `for: 30s` — если alert ещё `pending`/`normal`, подожди
~40 с после шага 7 и повтори.

```bash
make slo-verify
```

**Ожидаемо:** вывод серий и зелёный вердикт, exit-код `0`:

```
latency-серии по нодам: ['classify', 'policy-check']
cost-серии по нодам: ['classify', 'policy-check']
budget-эскалаций (set=base): 4
alert rule 'Per-node latency SLO': state=firing
────…
✅  VERIFY OK — per-node метрики скрейпятся Prometheus, alert rule 'Per-node latency SLO' Firing и называет просевшую ноду
```

## 9. Идемпотентность push — last-write, без распухания серий

Зачем: повторный push не должен плодить серии. Метрики — gauge, а push замещает группу
`job=authwise-batch, set=base` целиком (last-write). Проверяем, что число серий до и после
повторного push не растёт.

```bash
curl -s "http://localhost:9090/api/v1/query?query=aw_node_latency_ms_avg" | jq '.data.result | length'
make metrics-push >/dev/null
sleep 2
curl -s "http://localhost:9090/api/v1/query?query=aw_node_latency_ms_avg" | jq '.data.result | length'
curl -s "http://localhost:9091/api/v1/metrics" | jq '[.data[].labels | {job, set}] | unique'
```

**Ожидаемо:** оба `jq`-числа равны `2` (по серии на `classify` и `policy-check` — не удвоились);
последний `jq` — единственная группа `[{"job":"authwise-batch","set":"base"}]`. Реестр MLflow при
этом не трогается (метрики его не открывают).

## 10. Кадр витрины (ручной, не в церемонии): Grafana-дашборд + Firing-алерт

Зачем: north-star-кадр iter 4 — per-node SLO-дашборд и **сработавший алерт** в Grafana; это
визуальный материал для финального showcase-README, не доказательство (доказательство — шаг 8).

1. Открыть http://localhost:3002, войти `admin` / `lite-password`.
2. Dashboards → папка `authwise-lite` → дашборд SLO: панели latency/cost **по нодам** (`classify`,
   `policy-check`).
3. Alerting → Alert rules → `Per-node latency SLO`: состояние **Firing**, в labels — `node` с
   именем просевшей ноды.

**Ожидаемо:** дашборд с разбивкой по нодам и алерт в состоянии Firing. В церемонию закрытия шаг не
входит (UI — витрина, не доказательство).
