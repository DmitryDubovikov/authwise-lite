# Итерация 04 — Agent FinOps guardrails: per-node SLO alerting + runtime budget controls

> 🎯 **Цель проекта:** trajectory-eval — оценка *пути* многошагового агента, а не его финального
> ответа. Итерация 04 превращает измерение iter 3 в **guardrails**: per-node метрики уходят в
> Prometheus, Grafana-алерт называет просевшую ноду графа, а retry-loop графа гейтится **остатком
> бюджета рана в долларах** — исчерпание бюджета становится маршрутом (`escalate`), видимым на
> уровне траектории, а не исключением. Это единственная итерация с новым инструментом на весь
> проект — Prometheus + Grafana (правило 2).

## Зачем это (продукт и ценность)

Продукт (фикстура, но описываем как настоящий): payer **Northfield Health** маршрутизирует поток
Prior-Authorization-заявок — одобрить, дозапросить документы или эскалировать человеку — и держит
**сам маршрут** агента под операционным контролем. К iter 3 у команды уже есть эталон путей в
реестре, CI-гейт против регрессий маршрутизации и разбивка стоимости/задержки **по нодам** графа в
Langfuse. Но пока это только наблюдение: если policy-check начнёт тормозить, никто об этом не
узнает без ручного разглядывания трейсов; а если заявка застрянет в retry-loop, агент будет жечь
токены цикл за циклом, пока не упрётся в жёсткий потолок N. Ценность именно этой итерации в двух
guardrails. Во-первых, **SLO-алертинг**: per-node метрики уходят в Prometheus, а Grafana поднимает
алерт, который **называет конкретную просевшую ноду** — ops-инженер узнаёт «policy-check пробил
порог латентности», а не «в системе что-то медленно». Во-вторых, **runtime budget controls**:
у каждого рана есть бюджет в долларах, и retry-loop продолжается **только пока бюджет положителен**;
исчерпание уводит заявку в `escalate` (человек дешевле ещё одного LLM-цикла). Для payer'а это
разница между «агент однажды настроили и молимся, что он не разорит нас на зациклившейся заявке» и
«у каждого рана есть потолок расходов, а просадка ноды сама поднимает руку».

## 🧵 Что это дало резюме

Пункт north-star iter 4 — **Agent FinOps guardrails: per-node SLO alerting + runtime budget
controls** (пункты 4 и 5 красной нити) — стал демонстрируемым. Два артефакта-доказательства.
(1) `make budget-demo` с ужатым бюджетом через env уводит retry-заявку `PA-base-019` в
`escalate  [budget]` прямо в выводе CLI — исчерпание бюджета видно **как маршрут** в траектории;
с дефолтным бюджетом `make path-gate` по базовой пачке зелёный (golden-пути не изменились).
(2) `make metrics-push` заливает per-node latency/cost и счётчик budget-эскалаций в Prometheus, а
`make slo-verify` **запросом к Prometheus и Grafana API** (правило 9, не скрин UI) подтверждает:
серии `classify`/`policy-check` скрейпятся, а Grafana alert rule `Per-node latency SLO` в состоянии
**Firing** и несёт label `node` с именем просевшей ноды. Единственный новый инструмент проекта
(Prometheus + Grafana) подключён — стек-строка резюме `… · Prometheus/Grafana · …` теперь честна.

## TL;DR (простыми словами)

Было (после iter 3): граф ходит по маршрутам, гейт стережёт маршрут, cost/latency разложены по
нодам в Langfuse — но это только смотровое стекло, никаких ограничителей. Стало: добавили **два
предохранителя**. Первый — **бюджет рана**: перед каждым решением «крутить retry ещё раз?» граф
считает, сколько уже потрачено, и если бюджет исчерпан — уводит заявку к человеку (`escalate`)
вместо нового платного цикла. Дефолтный бюджет большой (маршруты не меняет), демо — через ужатый
бюджет в переменной окружения. Второй — **SLO-алертинг**: подняли Prometheus + Grafana (единственный
новый инструмент проекта), per-node метрики батча пушим в Prometheus через Pushgateway, а Grafana
держит правило-алерт на порог латентности, которое при превышении **загорается и называет ноду**.
Всё в replay, $0. `make check` и CI остаются офлайн — SLO-стек им не нужен.

## Что это за техника

**Runtime budget controls (бюджетный контроль рана)** — это FinOps-предохранитель: у прогона агента
есть лимит стоимости в долларах, и «дорогая» ветка графа (здесь — retry-loop policy-check)
продолжается только пока лимит не выбран. Ключевой сдвиг в том, что **исчерпание бюджета — это
маршрут, а не исключение**: заявка не падает с ошибкой, а честно уходит в `escalate` (к человеку) —
и это видно в траектории ровно так же, как любой другой путь. В нашем графе это одна строчка в
чистой domain-функции `decide`: ветка retry разрешается, только если `budget_remaining_usd > 0`.
Термины: *бюджет рана* (`AW_RUN_BUDGET_USD`) — потолок в USD на один прогон заявки; *остаток* —
бюджет минус уже потраченное к моменту решения (считаем `cost_usd` по накопленным `node_stats`);
*budget-эскалация* — факт, что решение разошлось с безлимитным (флаг `budget_escalated` в
`RunRecord`, для счётчика Prometheus; в замороженный `PathTrace` его не кладём — правило 3).

**Prometheus + Grafana + Pushgateway (SLO-алертинг)** — единственный новый инструмент проекта.
*Prometheus* — база временных рядов, которая **скрейпит** (периодически опрашивает) цели и хранит
метрики. Обычно цель — живой сервис, но у нас батч-прогон короткоживущий: пока Prometheus соберётся
скрейпить, процесс уже завершился. Поэтому берём *Pushgateway* — официальный компаньон Prometheus
для батч-джобов: джоб **пушит** метрики в него, Prometheus скрейпит уже Pushgateway. *Grafana* —
дашборды и алертинг поверх Prometheus; её *alert rule* периодически считает выражение (у нас
`max by (node) (aw_node_latency_ms_avg)`) и, если оно пробивает порог дольше `for`-окна, переходит
в состояние **Firing**. Термины: *метрика-gauge* — «моментальный снимок» значения (в отличие от
монотонного counter): наш push каждый раз перезаписывает last-write, а не накапливает; *провижининг
as-code* — datasource, дашборд и alert rule описаны YAML/JSON-файлами в `slo/` и монтируются в
контейнер, так что состояние Grafana целиком воспроизводимо из репо, без ручной настройки в UI;
*Firing* — алерт сработал (порог пробит дольше `for`).

Ничего из этого не «изобретено»: бюджетный гейт — одна ветка в существующей `decide`, а Prometheus/
Grafana подняты штатным Compose-профилем с provisioning-as-code. Ново — сам инструмент (Prometheus/
Grafana) и техника (бюджет как маршрут + per-node SLO поверх графа агента).

## Поток данных

Здесь **два независимых потока** — бюджетный гейт (внутри рана) и метрики (после рана). Начнём с
триггеров.

**Поток A — budget control (внутри графа, на каждый `decide`).** Оператор хочет прогнать базовую
пачку с ужатым бюджетом и набирает `make budget-demo` (это `AW_RUN_BUDGET_USD=0.00008 python -m
app.cli fixtures/requests-base.jsonl`). Заявка входит в граф; на каждом заходе в `decide_node` графу
нужно решить, крутить ли retry ещё раз. Чтобы это решить, ему нужен **остаток бюджета** — поэтому
`decide_node` берёт накопленные `node_stats` из стейта, считает по ним `spent_usd` (та же domain-
функция `cost_usd`, что и в Langfuse iter 3) и вычитает из `settings.run_budget_usd`. Остаток уходит
аргументом в чистую `decide()`: если policy-check вернул `missing_info`, потолок N ещё не выбран, но
остаток ≤ 0 — маршрут `escalate` вместо `retry`. Чтобы отличить эту эскалацию от «настоящей»,
`decide_node` рядом считает безлимитное решение (`budget_remaining_usd=inf`) и, если они разошлись,
поднимает флаг `budget_escalated` — он течёт в `RunRecord`, но **не** в `PathTrace` (тот заморожен).

```
make budget-demo
   │  AW_RUN_BUDGET_USD=0.00008
   ▼
classify → policy-check ─┐
   ▲                     │ missing_info
   │ retry (остаток > 0) ▼
   └──────────────── decide_node ── остаток ≤ 0 ──▶ escalate  [budget]
                          │
                          └─▶ budget_escalated=True → RunRecord (не в PathTrace)
```

**Поток B — метрики (после рана, батч → Prometheus → Grafana).** Оператор хочет увидеть per-node
SLO и набирает `make metrics-push`. Метрики **не гоняют граф заново** (контракт №3): скрипт
`metrics_push.py` читает уже записанный `runs/base.jsonl`, сворачивает его `aggregate_batch` в
per-node агрегаты (calls, latency avg, cost sum) плюс счётчик budget-эскалаций, и пушит их gauge'ами
в Pushgateway (одна группа `job=authwise-batch, set=base`, last-write). Prometheus скрейпит
Pushgateway каждые 5 с. Grafana каждые 10 с считает alert rule `max by (node) (aw_node_latency_ms_avg)`
против ужатого демо-порога 0.01 мс; латентность replay (~0.02 мс) его пробивает, и через `for: 30s`
правило переходит в **Firing** с label `node`. `make slo-verify` доказывает это запросом к обоим API.

```
runs/base.jsonl ──read──▶ metrics_push.py ──push(gauge)──▶ Pushgateway :9091
  (RunRecord, контракт №3)   (aggregate_batch)                    │ scrape 5s
                                                                  ▼
                                                          Prometheus :9090
                                                                  │ alert eval 10s
                                                                  ▼
                                                    Grafana :3002  alert rule → Firing
                                                                  ▲
                                              make slo-verify ── query API (правило 9)
```

| Инструмент | Что делает | Куда пишет |
|---|---|---|
| `decide_node` (граф) | считает остаток бюджета, гейтит ветку retry, поднимает флаг `budget_escalated` | стейт графа → `RunRecord.budget_escalated` |
| `app.cli` / `make budget-demo` | прогоняет пачку в replay, печатает пути с маркером `[budget]`, пишет `RunRecord` (полный прогон) | stdout + `runs/<set>.jsonl` |
| `scripts/metrics_push.py` | читает `RunRecord`, сворачивает per-node агрегаты, пушит gauge'ы | Pushgateway `:9091` (group `set=base`) |
| Prometheus | скрейпит Pushgateway каждые 5 с | свои временные ряды `:9090` |
| Grafana alert rule | считает `max by (node)(latency)` против порога, держит состояние | Firing/OK в Grafana `:3002` |
| `scripts/slo_verify.py` | verify the store: per-node серии из Prometheus API + alert Firing из Grafana API | stdout (exit 0/1) |

**Честные оговорки — чего в этой итерации НЕ происходит.** (1) SLO-порог **демонстрационный**
(0.01 мс, помечен `# aw-lite:`): в replay латентность ~0, снимать реальные SLO не с чего — в проде
порог калибруется по live-замерам. (2) **Alertmanager не поднимаем** — уведомления наружу (Slack/
почта) не нужны, кадр витрины — Firing в самой Grafana. (3) Дефолтный бюджет `$0.05` маршруты **не
меняет** — он с ~350× запасом над самым дорогим golden-раном; budget-эскалация видна только под
ужатым бюджетом из env. (4) `PathTrace` **не расширяли** — факт бюджет-эскалации живёт флагом в
`RunRecord`, не в траектории (правило 3, граф заморожен).

## Карта «где в коде»

> Номера строк — ориентир на момент закрытия iter 4; надёжнее искать по именам символов.

1. **Бюджетный гейт в `decide` — файл `app/domain/decide.py:14`.** Чистая domain-функция получила
   новый keyword-аргумент `budget_remaining_usd`. Логика: `missing_info` с невыбранным потолком N
   разрешает `retry` **только при положительном остатке**, иначе — `escalate`. Исчерпанный потолок
   по-прежнему бьёт бюджет (терминал `request-info`), потому что нового LLM-цикла всё равно нет.
   Новых веток не добавилось — переиспользуется существующая `escalate`.

   ```python
   def decide(
       policy: PolicyCheckResult, *, retry_cycles: int, retry_limit: int,
       budget_remaining_usd: float,
   ) -> Decision:
       if policy.status == "sufficient":
           return "approve"
       if policy.status == "out_of_policy":
           return "escalate"
       # missing_info: до-запрос, пока не исчерпаны ни потолок N, ни бюджет рана
       if retry_cycles >= retry_limit:
           return "request-info"
       return "retry" if budget_remaining_usd > 0 else "escalate"
   ```

2. **Расчёт остатка и флаг эскалации — файл `app/workflow/graph.py:105` (`decide_node`).** Workflow-
   слой считает остаток (`run_budget_usd − spent_usd(node_stats)`) и передаёт в domain. Флаг
   `budget_escalated` определяется как **расхождение с безлимитным решением** — так он ловит именно
   бюджетную эскалацию, а не любую (`out_of_policy` эскалирует и без бюджета).

   ```python
   def decide_node(state: PAState, config: RunnableConfig) -> dict[str, object]:
       settings = _settings(config)
       remaining = settings.run_budget_usd - spent_usd(state["node_stats"], settings)
       retry_cycles = state.get("retry_cycles", 0)
       decision = decide(state["policy"], retry_cycles=retry_cycles,
                         retry_limit=settings.retry_limit, budget_remaining_usd=remaining)
       unbounded = decide(state["policy"], retry_cycles=retry_cycles,
                         retry_limit=settings.retry_limit, budget_remaining_usd=math.inf)
       return {"decision": decision, "budget_escalated": decision != unbounded, "nodes": ["decide"]}
   ```

3. **Стоимость рана — файл `app/workflow/costs.py:21` (`spent_usd`).** Тонкий wiring поверх domain
   `cost_usd` (контракт №5): тир берётся из `NodeStat` (зафиксирован в момент вызова — cost прошлого
   прогона не переоценивается текущим env), цены — из `llm-tiers.yaml`. `spent_usd` суммирует по
   накопленным статам — из него `decide_node` выводит остаток.

   ```python
   def spent_usd(stats: Iterable[NodeStat], settings: Settings) -> float:
       """Потрачено раном к текущему моменту — из него decide_node выводит остаток бюджета."""
       return sum(stat_cost_usd(stat, settings) or 0.0 for stat in stats)
   ```

4. **Per-node агрегаты батча — файл `app/workflow/metrics.py:30` (`aggregate_batch`).** Чистая
   свёртка `RunRecord` → `BatchAggregate`: по каждой ноде — число вызовов, средняя латентность,
   суммарный cost; плюс общий счётчик `budget_escalations` и число ранов. I/O здесь нет — чтение
   JSONL и push живут в скрипте.

   ```python
   def aggregate_batch(records: Iterable[RunRecord], *, settings: Settings) -> BatchAggregate:
       by_node: dict[str, list[NodeStat]] = defaultdict(list)
       runs = 0; budget_escalations = 0
       for record in records:
           runs += 1
           budget_escalations += record.budget_escalated
           for stat in record.node_stats:
               by_node[stat.node].append(stat)
       nodes = {node: NodeAggregate(calls=len(stats),
                   latency_ms_avg=sum(s.latency_ms for s in stats) / len(stats),
                   cost_usd=sum(stat_cost_usd(s, settings) or 0.0 for s in stats))
                for node, stats in by_node.items()}
       return BatchAggregate(runs=runs, budget_escalations=budget_escalations, nodes=nodes)
   ```

5. **Push в Pushgateway — файл `scripts/metrics_push.py` (`main`).** Тонкий транспорт: читает
   `records_path(settings)`, сворачивает `aggregate_batch`, заводит `Gauge`'ы (не `Counter` —
   значения снапшот последнего батча) и пушит группу `job=authwise-batch` с `grouping_key={set}`,
   чтобы наборы кассет сосуществовали, а повторный пуш замещал только свою группу (идемпотентность).

   ```python
   push_to_gateway(settings.pushgateway_url, job="authwise-batch",
                   grouping_key={"set": cassette_set}, registry=registry)
   ```

6. **Verify the store — файл `scripts/slo_verify.py:51` (`main`).** Доказательство запросами к API
   (правило 9): Prometheus HTTP API отдаёт per-node latency/cost-серии и счётчик эскалаций, Grafana
   Prometheus-совместимый API отдаёт состояние alert rule. Зелёный вердикт требует, чтобы серии
   LLM-нод существовали **и** alert был `firing`.

   ```python
   def _alert_state(settings: Settings) -> str | None:
       url = f"{settings.grafana_url}/api/prometheus/grafana/api/v1/rules"
       auth = (settings.grafana_user, settings.grafana_password.get_secret_value())
       payload = _get_json(url, auth=auth)
       for group in payload["data"]["groups"]:
           for rule in group["rules"]:
               if rule["name"] == ALERT_TITLE:
                   return str(rule["state"])
       return None
   ```

7. **Бюджет в `Settings` — файл `app/config.py:27`.** `run_budget_usd: float = 0.05` — дефолт с
   ~350× запасом над самым дорогим golden-раном (golden-пути не меняет); ниже — URL/креды SLO-стека
   (`pushgateway_url`, `prometheus_url`, `grafana_url`, `grafana_user`, `grafana_password`),
   admin/lite-password — dev-сид, не секрет.

8. **`NodeStat.tier` + `RunRecord.budget_escalated` — файлы `app/domain/schemas.py:44`,
   `app/workflow/runner.py:24`, `records_path` — `runner.py:90`.** В `NodeStat` добавлено поле `tier`
   (тир фиксируется в момент вызова, чтобы cost не переоценивался env); `RunRecord` понёс флаг
   `budget_escalated` (сериализуется в JSONL); `records_path(settings)` централизовал конвенцию
   имени артефакта `runs/<set>.jsonl` — одно место вместо копий в CLI/path-gate/metrics-push.

9. **Compose-профиль `slo` + провижининг — `docker-compose.yml` (сервисы `prometheus`/`pushgateway`/
   `grafana`, профиль `slo`) и каталог `slo/`.** Prometheus скрейпит только Pushgateway
   (`slo/prometheus.yml`, `honor_labels: true`); Grafana целиком provisioning-as-code — datasource
   с зашитым uid `aw-prometheus`, файловый провайдер дашбордов и Grafana-managed alert rule
   (`slo/grafana/provisioning/alerting/aw-slo.yml`) с демо-порогом `# aw-lite: 0.01ms`. Host-порты:
   Grafana 3002, Prometheus 9090, Pushgateway 9091 (3000/3001 заняты). Makefile-цели `slo-up`,
   `metrics-push`, `budget-demo`, `slo-verify`.
