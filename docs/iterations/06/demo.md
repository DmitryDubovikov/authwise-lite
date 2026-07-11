# Демо итерации 06 — Routing-policy as versioned artifact (пиннинг промпт-версий)

Прогон доказывает, что **маршрутизирующая конфигурация агента материализована как
версионируемый артефакт реестра** (пункт 7 north-star): промпты обеих LLM-нод — версионируемые
объекты в MLflow Prompt Registry, а «routing-policy» — версия приложения, **пинящая их конкретные
версии**, с alias `champion`/`challenger` и атомарным ручным swap. Ценность за пределами демо: до
этого «какая логика маршрутизации сейчас в проде» была вопросом к git-хешу; теперь это именованный
объект в реестре, который ops-инженер переключает одним swap alias, а не выкаткой кода. Демо
показывает по очереди: (1) статика и тесты остаются offline; (2) точечные тесты техники; (3) сам
стор подтверждает пины и alias по MLflow API (правило 9), и сид **идемпотентен** — повторный не
распухает и не откатывает swap; (4) swap атомарно обменивает роли и возвращается назад; (5)
запиненные шаблоны реально доезжают из реестра до нод графа, не меняя путей ($0).

Все команды выполняются из корня репо: `/Users/dd/projects/pet/authwise-lite` (бинарь `uv` —
`/Users/dd/.local/bin/uv`). Всё демо — **replay/офлайн-стор, $0**; live-шагов у этой итерации нет
(реестр наполняется теми же текстами промптов, что в коде, — деньги не тратятся).

## 1. Статический гейт (то, что гоняет CI) — стек не нужен

Зачем: `make check` — ровно то, что гоняет CI. Тесты routing-policy работают на герметичном sqlite
во временном каталоге, поэтому живут в обычном pytest без поднятого MLflow-сервера и без сети.

```bash
make check
```

**Ожидаемо:** все шаги зелёные (ruff check, ruff format, mypy, pytest), последняя строка pytest —
`69 passed`.

## 2. Точечные тесты техники iter 6

Зачем: убедиться, что версионирование ведёт себя как заявлено — сид идемпотентен и не откатывает
swap, `resolve` кросс-чекает пины, а alias-загрузка реально доезжает до нод графа (а не молча
берёт промпт из кода).

```bash
uv run pytest tests/test_policy.py -v
```

**Ожидаемо:** `6 passed`; в списке — `test_seed_is_idempotent`,
`test_champion_pins_code_prompts_challenger_rubber_stamp`,
`test_swap_exchanges_aliases_and_seed_keeps_swap`, `test_resolve_missing_alias_returns_none`,
`test_load_bundle_feeds_graph_without_changing_paths`, `test_bundle_templates_actually_reach_nodes`.

## 3. Поднять MLflow и засеять routing-policy (идемпотентно)

Зачем: routing-policy живёт в MLflow (том же сторе, что golden-сет iter 1). `policy-seed`
наполняет реестр промптами, версиями-политиками с пинами и alias — и обязан быть **идемпотентным**:
повторный сид не должен ни плодить версии, ни откатывать сделанный swap.

```bash
make up
docker compose ps --format '{{.Name}} {{.Status}}' | grep mlflow
make policy-seed
make policy-seed
```

**Ожидаемо:** `authwise-lite-mlflow-1 … Up`. Оба прогона `policy-seed` печатают **одно и то же** —
версии не растут, а alias помечены как не тронутые:

```
prompt pa-classify: v1
prompt pa-policy-check: v1 (код), v2 (rubber-stamp, challenger-фикстура)
pa-routing-policy v1: classify v1 + policy-check v1
pa-routing-policy v2: classify v1 + policy-check v2
alias champion: уже существовал — не тронут (swap не откатывается)
alias challenger: уже существовал — не тронут (swap не откатывается)
```

(На самом первом сиде пустого стора те же две строки alias будут `поставлен` — дальше уже
`уже существовал`.)

## 4. Verify the store (правило 9): alias, пины, шаблоны — запросом к MLflow

Зачем: заставить **стор**, а не скрин UI, подтвердить, что routing-policy — реальный
двухуровневый артефакт: alias разрешаются в версии registered model, каждая версия пинит
заявленные версии промптов, и `params` сходятся с тегом `mlflow.linkedPrompts`.

```bash
make policy-verify
```

**Ожидаемо:**

```
champion → pa-routing-policy v1 (pa-classify v1, pa-policy-check v1)
challenger → pa-routing-policy v2 (pa-classify v1, pa-policy-check v2)
────────────────────────────────────────────────────────────
✅  VERIFY OK — pa-routing-policy: alias разрешаются, пины params ↔ linkedPrompts сходятся, политики различаются policy-check
```

Тот же факт «в сыром виде» из MLflow REST (вспомогательная проверка, не основной путь — показывает,
что alias и пины лежат в сторе, а не рисуются нашим кодом):

```bash
curl -s "http://localhost:5051/api/2.0/mlflow/registered-models/get?name=pa-routing-policy" | jq '.registered_model.aliases'
```

**Ожидаемо:** массив с `{"alias":"challenger","version":"2"}` и `{"alias":"champion","version":"1"}`.

## 5. Ручной swap champion ↔ challenger — и возврат

Зачем: это и есть «переключить прод одним swap alias». Swap атомарно (для каждого alias) меняет,
какая версия routing-policy — champion; повторный swap возвращает исходное (обмен, не
промоушен-механика). Между шагами verify показывает обмен по данным стора.

```bash
make policy-swap
make policy-verify
make policy-swap
make policy-verify
```

**Ожидаемо:** первый `policy-swap` печатает
`pa-routing-policy: champion → v2, challenger → v1 (обмен; …)`, и следующий `policy-verify`
показывает `champion → … v2 (…, pa-policy-check v2)` / `challenger → … v1 (…, pa-policy-check v1)`.
Второй `policy-swap` возвращает `champion → v1, challenger → v2`, и финальный `policy-verify` снова
показывает исходное состояние из шага 4. Оба verify — `✅ VERIFY OK`.

## 6. Alias-загрузка: запиненные шаблоны из реестра доезжают до графа ($0)

Зачем: доказать, что routing-policy — не только запись в реестре, но и **рабочая конфигурация**:
при `AW_ROUTING_POLICY_ALIAS=champion` CLI резолвит alias, тянет запиненные шаблоны из Prompt
Registry и прогоняет пачку **на них**, а не на коде. И — что это существование, а не подмена
поведения: пути обязаны совпасть с обычным replay (кассеты ключуются `(request_id, node, attempt)`,
контракт №4, а не текстом промпта).

```bash
make replay-base-champion | head -4
```

**Ожидаемо:** первая строка называет загруженную политику, дальше — путь каждой заявки:

```
routing-policy: champion → v1 (pa-classify v1, pa-policy-check v1)
PA-base-001: classify → policy-check → approve
PA-base-002: classify → policy-check → approve
PA-base-003: classify → policy-check → approve
```

Проверка «пути не изменились» — сравнить с обычным replay на промптах из кода (различий быть не
должно):

```bash
make replay-base-champion | grep '^PA-base' > /tmp/champ.txt
make replay-base          | grep '^PA-base' > /tmp/code.txt
diff /tmp/champ.txt /tmp/code.txt && echo "ПУТИ ИДЕНТИЧНЫ ✓"
```

**Ожидаемо:** `diff` не печатает различий, последняя строка — `ПУТИ ИДЕНТИЧНЫ ✓` (30 заявок,
терминалы `22 approve / 4 escalate / 4 request-info` в обоих случаях).

## 7. (Витрина, опционально) MLflow UI глазами

Зачем: verify доказал всё по API; UI — только чтобы посмотреть кадр витрины (правило 8).

Открыть http://localhost:5051 → **Models** → `pa-routing-policy`.

**Ожидаемо:** две версии — v1 под alias `champion`, v2 под `challenger`; у каждой в
`params`/linked prompts виден пин (v1: pa-classify v1 + pa-policy-check v1; v2: pa-classify v1 +
pa-policy-check v2). В **Prompts** — `pa-classify` (1 версия) и `pa-policy-check` (2 версии: код +
rubber-stamp).
