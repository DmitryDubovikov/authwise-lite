# Итерация 00 — каркас: control plane + branching-граф

> 🎯 **Цель проекта:** trajectory-eval — оценка *пути* многошагового агента, а не его финального
> ответа. Итерация 00 закладывает объект измерения: граф с реальным ветвлением и retry-циклом,
> который возвращает свой путь как типизированное значение.

## Зачем это (продукт и ценность)

Продукт (фикстура, но описываем как настоящий): payer **Northfield Health** получает поток
Prior-Authorization-заявок — «одобрите МРТ», «одобрите препарат», — и каждую нужно маршрутизировать
без ручного разбора: одобрить, дозапросить недостающие документы или эскалировать человеку.
Бизнес-ценность всего проекта — ops-инженеру payer'а нужен операционный контроль над **самим
маршрутом** агента: эталон путей, CI-гейт против регрессий маршрутизации, стоимость каждого шага,
алерт на дрейф веток. Ценность именно этой итерации: агент-маршрутизатор теперь **существует и
рассказывает, как он шёл** — по каждой заявке видно, какая ветка сработала и сколько раз агент
дозапрашивал документы. Это фундамент: всё, что проект будет версионировать, гейтить и мониторить
дальше, — ровно эта запись пути.

## 🧵 Что это дало резюме

Пункт red-thread iter 0 — **«Branching-граф с реальным ветвлением заложен»** — демонстрируем:
`make smoke` печатает четыре разных пути (все три терминала + retry-цикл), а pytest ассертит их
по `PathTrace`, не по логам. Это пререквизит всех восьми north-star-практик, сам по себе строкой
резюме не является.

## TL;DR (простыми словами)

Было: пустой репозиторий с конституцией и роадмапом. Стало: работающий проект, в котором
LangGraph-агент прогоняет PA-заявку через три шага (`classify → policy-check → decide`) и
возвращает вместе с вердиктом свой **путь** — ветку и число retry-циклов. Всё гоняется офлайн
за $0: ответы LLM читаются из кассет, записанных заранее. Плюс перенесённый из сиблингов
обвес: uv/ruff/pytest, тиры моделей с пином снапшотов, MLflow в Docker, CI-скелет на GitHub.

## Что это за техника

**Branching-граф с retry-циклом** — это LangGraph-граф, где решение о маршруте принимает не
LLM-нода, а детерминированная функция `decide()` над её структурированным выходом: `sufficient`
→ approve, `out_of_policy` → escalate, `missing_info` → ещё один цикл до-запроса документов,
пока не исчерпан потолок N=2. *PathTrace* — типизированная запись пройденного пути:
`{branch, retry_cycles, nodes}`; она замороженна конституцией и является единственным источником
истины для будущих golden/CI-ассертов. *Кассеты* — записанные JSON-ответы LLM: режим `replay`
(дефолт) читает их с диска и никогда не бьёт в сеть, поэтому путь заявки воспроизводим и бесплатен.
Ключ кассеты — `(request_id, node, attempt)`, а не хэш содержимого запроса: смена текста промпта
не рвёт replay (это структурная заготовка под демо-регрессию iter 2).

## Поток данных

Оператор хочет увидеть, как агент маршрутизирует smoke-заявки, и набирает `make smoke`
(внутри — `uv run python -m app.cli fixtures/requests-smoke.jsonl`). CLI читает JSONL-фикстуру
и для каждой заявки просит workflow-слой прогнать её через граф. Графу, чтобы дойти до решения,
нужны два LLM-вердикта: нода `classify` определяет тип кейса, нода `policy-check` — достаточно
ли документов. Обе зовут единственный шов к LLM — `route(tier, …)`, который в replay-режиме
вместо сети открывает кассету `cassettes/smoke/<request_id>__<node>__a<attempt>.json`. Дальше
`decide` (чистая функция, без LLM) выбирает ветку; если документов не хватает — нода
`request-info` «получает» следующий пакет документов из фикстуры и возвращает заявку в
`policy-check`, увеличив счётчик циклов. Когда граф приходит в терминал, boundary-функция
`run_pa_request()` собирает из финального стейта `PathTrace` и отдаёт его CLI, который печатает
строку пути.

```
оператор: make smoke
    │
    ▼
CLI (app/cli/main.py) ── читает fixtures/requests-smoke.jsonl
    │
    ▼
run_pa_request()  (workflow, boundary)
    │
    ▼
LangGraph-граф:  classify ──► policy-check ──► decide ──┬─► approve ─────────┐
                     │             ▲                    ├─► escalate ────────┤► END
                     │             │ ↻ ≤2               ├─► request-info ────┘
                     ▼             │                    └─► retry
                  route()      request-info ◄───────────────┘
                     │
                     ▼
        cassettes/smoke/*.json  (replay: чтение с диска, $0, сети нет)

    результат: PathTrace {branch, retry_cycles, nodes} ──► CLI печатает путь
```

| Инструмент | Что делает | Куда пишет |
|---|---|---|
| CLI (`python -m app.cli`) | гонит заявки фикстуры через граф | stdout: `PA-smoke-002: classify → policy-check → request-info ↻1 → approve` |
| LangGraph | исполняет граф, копит стейт (включая посещённые ноды) | никуда — финальный стейт возвращается значением |
| `route()` + кассеты | подменяет LLM-вызов чтением кассеты (replay) | при `record` — пишет кассету в `cassettes/<set>/`; в replay — ничего |
| `scripts/author_smoke_cassettes.py` | генерит авторские кассеты smoke-набора ($0) | `cassettes/smoke/*.json` (11 файлов, с синтетическим `usage`) |
| MLflow (Docker, `make up`) | пока только поднят и отвечает на `:5051` | `mlflow-data/` (sqlite); **пуст — сущности появятся в iter 1** |

Честные оговорки: в этой итерации **нет** ни MLflow-сущностей (golden-сет — iter 1), ни
CI path-gate (iter 2), ни телеметрии/дашбордов (iter 3–5). Кассеты — авторские: их содержимое
придумано скриптом, `usage` синтетический; настоящий record-прогон — плановый расход iter 1.

Слои и направление зависимостей (правило 6 конституции):

```
cli (транспорт, тонкий)
 └─► workflow (graph.py, prompts.py, fixtures.py)
      ├─► domain (schemas, decide, path) — чистые функции, без I/O
      └─► llm (router → tiers, cassettes) — поперечный слой
                │
                └─ env только через Settings (app/config.py, префикс AW_)
```

## Карта «где в коде»

Номера строк — ориентир на момент итерации; надёжнее искать по именам символов.

1. **`PathTrace` — замороженный domain-объект пути** — `app/domain/path.py:14-19`.
   Дата-класс с тремя полями; `nodes` — информационное поле для витрины, в ассертах участвует
   только пара `(branch, retry_cycles)`. Рядом живёт `render_path()`, собирающий витринную
   строку пути (терминальный `request-info` не задваивается).

   ```python
   Branch = Literal["approve", "request-info", "escalate"]

   @dataclass(frozen=True)
   class PathTrace:
       branch: Branch
       retry_cycles: int  # число прокруток retry-loop до терминала
       nodes: tuple[str, ...]  # информационное поле — в golden/CI не ассертится
   ```

2. **`decide()` — детерминированное ветвление** — `app/domain/decide.py:16-23`. Чистая функция
   над структурированным выходом policy-check и счётчиком циклов; LLM в решении о маршруте не
   участвует. С iter 4 сюда добавится остаток бюджета рана.

   ```python
   def decide(policy: PolicyCheckResult, *, retry_cycles: int, retry_limit: int) -> Decision:
       if policy.status == "sufficient":
           return "approve"
       if policy.status == "out_of_policy":
           return "escalate"
       return "retry" if retry_cycles < retry_limit else "request-info"
   ```

3. **Граф и boundary** — `app/workflow/graph.py` (`build_pa_graph()` ~строка 100,
   `run_pa_request()` ~строка 130). Паттерн policywise: решение пишется нодой `decide` в стейт,
   условное ребро — тривиальный lookup; deps идут через `config["configurable"]`, не через
   стейт. Retry-цикл — ребро `request-info → policy-check`. Boundary собирает `PathTrace` из
   финального стейта.

   ```python
   builder.add_conditional_edges(
       "decide",
       route_decision,
       {"retry": "request-info", "approve": END, "escalate": END, "request-info": END},
   )
   builder.add_edge("request-info", "policy-check")
   ```

4. **`route()` — единственный шов к LLM** — `app/llm/router.py:26-50`. Резолвит тир в
   запиннённый снапшот, в replay читает кассету, в record/live делает один голый
   `litellm.acompletion` с `temperature=0` и выключенной телеметрией (дисциплина правила 5,
   закреплена механическим тестом `tests/test_litellm_discipline.py`).

5. **Кассеты с ключом `(request_id, node, attempt)`** — `app/llm/cassettes.py:22-24`. Формат
   хранит `usage` ответа — из него в iter 3–4 считается per-node cost. Replay-промах — громкая
   ошибка, не тихий фолбэк.

   ```python
   def cassette_path(root: Path, set_name: str, request_id: str, node: str, attempt: int) -> Path:
       return root / set_name / f"{request_id}__{node}__a{attempt}.json"
   ```

6. **Тиры с пин-гейтом и ценами** — `llm-tiers.yaml` + `app/llm/tiers.py:21-33`. Загрузчик
   отвергает модель без датированного суффикса `-YYYY-MM-DD`; цены токенов лежат рядом с
   моделями (контракт №5 — из них плюс `usage` кассет считается стоимость ноды).

7. **`Settings` — единственный шлюз к env** — `app/config.py:15-31`. Префикс `AW_`
   (`AW_LLM_MODE`, `AW_CASSETTE_SET`, `AW_RETRY_LIMIT`, `AW_TIER_*`); ключ OpenAI — `SecretStr`.
   MLflow слушает `http://localhost:5051` — 5050 занят MLflow сиблинга triagewise-lite.

8. **Smoke-фикстура и авторские кассеты** — `fixtures/requests-smoke.jsonl` (4 заявки: approve /
   ↻1→approve / escalate / ↻2→терминальный request-info) и `scripts/author_smoke_cassettes.py`,
   который строит содержимое кассет domain-схемами (`Classification`, `PolicyCheckResult`) —
   кассета валидна по построению. Помечено `# aw-lite: авторские кассеты → реальный record в iter 1`.

9. **Тесты пути** — `tests/test_smoke_paths.py`: module-scoped фикстура один раз гонит все
   4 заявки и ассертит `(branch, retry_cycles)` по `EXPECTED`; отдельный тест проверяет, что
   retry-цикл честно повторно посещает `policy-check`.
