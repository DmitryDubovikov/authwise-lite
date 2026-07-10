# Демо итерации 03 — Per-node cost/latency attribution (Langfuse)

Прогон доказывает третью north-star-практику проекта — **per-node cost/latency attribution**: у
команды появилась разбивка стоимости и задержки **по шагам агента**, а не по рану целиком. Ценность
за пределами демо: это измерительный фундамент agent-level FinOps — прежде чем ставить SLO на
конкретную ноду и ловить, какой шаг просел (iter 4), нужно уметь атрибутировать расход к ноде.
Демо показывает по очереди: (1) по умолчанию трейсинг — чистый no-op, `make check` и обычный replay
langfuse даже не импортируют; (2) с поднятым Langfuse и ключами прогон пачки даёт **трейс на заявку
со спанами-нодами и generation'ами с usage/cost**; (3) сам стор это подтверждает запросом к API
(правило 9, не скрин UI); (4) per-node usage/latency лёг и в `RunRecord`/JSONL (контракт №3) — в том
числе три вызова policy-check на retry-заявке.

Все команды выполняются из корня репо: `/Users/dd/projects/pet/authwise-lite`. Вся итерация
**бесплатная** — LLM не зовётся, всё в replay ($0). Live-шагов нет.

## 1. Окружение

Зачем: остальные шаги гоняются через `uv run` из локального venv; iter 3 добавила зависимости
`langfuse` и `langchain` (для `CallbackHandler`).

```bash
uv sync --extra dev
```

**Ожидаемо:** завершается без ошибок; в выводе видно установку `langfuse` и `langchain` (venv
`.venv/` обновлён из `uv.lock`).

## 2. Статический гейт (то, что гоняет CI) — трейсинг здесь ВЫКЛЮЧЕН

Зачем: `make check` — ровно то, что гоняет CI, и оно должно оставаться офлайн и бесплатным. Трейсинг
по умолчанию — no-op: без ключей `AW_LANGFUSE_*` langfuse не импортируется, сервер не нужен. Среди
тестов — `tests/test_tracing.py`, который это и стережёт (в т.ч. что полный replay-прогон графа не
затягивает `langfuse` в `sys.modules`), и `tests/test_cost.py` (математика `cost_usd`).

```bash
make check
```

**Ожидаемо:** все шаги зелёные (ruff check, ruff format, mypy, pytest), последняя строка pytest —
`46 passed`. Никакого docker/сети не требуется.

## 3. Точечные тесты техники iter 3

Зачем: сузить до тестов именно этой итерации — стоимость, no-op-гейт трейсинга, per-node `node_stats`.

```bash
uv run pytest tests/test_cost.py tests/test_tracing.py \
  tests/test_smoke_paths.py::test_node_stats_attribute_every_llm_call -v
```

**Ожидаемо:** `6 passed`. В частности `test_disabled_tracing_does_not_import_langfuse` (lazy-import
гейт) и `test_node_stats_attribute_every_llm_call` (по записи `node_stats` на каждый LLM-вызов:
`classify#1, policy-check#1, policy-check#2, policy-check#3` на retry-заявке).

## 4. Поднять приёмник трейсов (Langfuse-стек, профиль `obs`)

Зачем: атрибуцию по нодам показываем в Langfuse; его нужно поднять. Профиль `obs` держит стек
отдельно от лёгкого `make up` (MLflow): поднимаются langfuse-web/worker + свои pg/clickhouse/redis/
minio. Ключи проекта детерминированы через `LANGFUSE_INIT_*` в compose (`pk-aw`/`sk-aw`) — трейсинг
и verify знают креды заранее.

```bash
make obs-up
docker compose --profile obs ps
```

**Ожидаемо:** `make obs-up` поднимает 7 сервисов `langfuse-*` (+ уже поднятый `mlflow`, если был);
`ps` показывает `langfuse-web` в статусе `Up` с портом `0.0.0.0:3001->3000/tcp`. Первый подъём
clickhouse/pg занимает 30–60 с — если следующий шаг скажет «нет трейсов», подожди, пока web
станет `Up`. UI (для витрины, не для доказательства): http://localhost:3001 — вход
`dev@authwise.lite` / `lite-password`.

## 5. Прогнать базовую пачку с трейсингом — $0, в Langfuse льются трейсы

Зачем: это и есть техника iter 3 в действии — прогон каждой заявки становится трейсом со спанами по
нодам и generation'ами с usage/cost. `make trace-base` = обычный replay базовой пачки, но с
выставленными ключами `AW_LANGFUSE_*`, поэтому трейсинг включается. Всё так же $0 (кассеты, сеть в
LLM не идёт), трейсы уходят в локальный Langfuse.

```bash
make trace-base
```

**Ожидаемо:** те же 30 строк путей, что и у обычного `make replay-base` (`PA-base-001: classify →
policy-check → approve` … `PA-base-019: classify → policy-check → request-info ↻2` …) — трейсинг
маршрут не меняет (правило 6). Разница — теперь в Langfuse появились 30 трейсов. На границе пачки
`run_batch` дожимает батч (`tracing.flush()`), поэтому к концу команды трейсы отправлены.

## 6. Verify the store (правило 9) — атрибуция по нодам, запросом к API

Зачем: доказываем **из стора, а не из UI**. Скрипт берёт свежий трейс через Langfuse public API и
ассертит: спаны названы нодами графа (атрибуция **по ноде**, не по всему run); по каждой LLM-ноде
есть generation; **generation вложен в спан своей одноимённой ноды**; у каждого generation есть
usage и наш cost из `llm-tiers.yaml`.

```bash
make langfuse-verify
```

**Ожидаемо:** сначала по строке на каждый generation свежего трейса, например
`classify: model=gpt-4.1-nano-2025-04-14 in=127 out=15 cost=$0.000019` и
`policy-check: model=gpt-4.1-nano-2025-04-14 in=187 out=49 cost=$0.000038`; затем
`✅  VERIFY OK — трейс <id>: спаны атрибутированы по нодам графа, N generation с usage и cost из
llm-tiers.yaml`, exit-код `0`. Если попался retry-трейс (например только что прогнанный
`PA-base-019`), generation'ов policy-check будет три — видно, что retry-loop дороже. Если скрипт
скажет «в Langfuse нет трейсов» — worker ещё не проглотил батч, подожди 2–3 с и повтори.

## 7. Per-node usage/latency в артефакте прогона (контракт №3)

Зачем: атрибуция живёт не только в Langfuse — per-node usage/latency лёг и в `RunRecord`/JSONL,
который в iter 4/5 читают Prometheus и Phoenix (не гоняя граф заново). Показать сам артефакт:
`node_stats` с записью на каждый LLM-вызов, включая три policy-check на retry-заявке. JSONL пишет
`make path-gate` (CLI из шага 5 печатает пути, но файл не пишет — его пишет гейт-транспорт).

```bash
make path-gate >/dev/null
grep 'PA-base-019' runs/base.jsonl \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print([(s['node'], s['attempt'], s['usage']['total_tokens'], round(s['latency_ms'],3)) for s in d['node_stats']])"
```

**Ожидаемо:** список из четырёх записей —
`[('classify', 1, 139, …), ('policy-check', 1, …, …), ('policy-check', 2, …, …), ('policy-check', 3, …, …)]`:
per-node usage (`total_tokens` из кассеты) и `latency_ms` на каждый LLM-вызов заявки `PA-base-019`
(retry ↻2 → policy-check дёрнулся трижды). Латентность в replay ≈ сотые доли мс (чтение кассеты с
диска) — это ожидаемо, осмысленные абсолютные задержки будут при live; для существования атрибуции
достаточно, что поле есть и привязано к ноде. Каталог `runs/` gitignored.

## 8. Идемпотентность / append-only (вспомогательная проверка)

Зачем: убедиться, что повторный прогон трейсинга безопасен. Трейсы — append-only лог наблюдаемости:
повторный `make trace-base` не мутирует реестр (MLflow вообще не открывается) и не портит прошлые
трейсы — просто добавляет новые, а verify остаётся зелёным.

```bash
make trace-base >/dev/null && make langfuse-verify | tail -1
```

**Ожидаемо:** `✅  VERIFY OK — трейс <НОВЫЙ id> …` — id отличается от шага 6 (append-only: новый
прогон = новые трейсы), вердикт по-прежнему зелёный. Alias/версии MLflow не двигаются, потому что
трейсинг их не касается.

## 9. Кадр витрины (ручной, не в церемонии): Langfuse Agent Graph

Зачем: north-star-кадр iter 3 — **Agent Graph** с реально пройденным маршрутом и cost/latency по
нодам; именно ради него подключались через `CallbackHandler`, а не голый OTel. Это визуальный
материал для финального showcase-README, не доказательство (доказательство — шаг 6).

1. Открыть http://localhost:3001, войти `dev@authwise.lite` / `lite-password`, проект `authwise-lite`.
2. Tracing → выбрать свежий трейс (напр. `PA-base-019`) → вкладка **Graph**: виден маршрут
   `classify → policy-check (×3) → …` со спанами-нодами; у generation'ов — model, tokens, cost.

**Ожидаемо:** дерево спанов, названных нодами графа, и Agent Graph-вид с маршрутом. В церемонию
закрытия шаг не входит (UI — витрина, не доказательство).
