# Решения по стеку

> Полные формулировки развилок и north-star — в `CLAUDE.md`; порядок итераций — в `ROADMAP.md`.
> Здесь — концентрат для ревью: что в ядре, где граница исполнения, сквозные конвенции.

## В ядре

- **LangGraph** — граф `classify → policy-check → decide{approve | request-info (↻≤2) | escalate}`,
  заморожен после iter 0. Паттерн policywise: решение пишется нодой в стейт, условное ребро —
  тривиальный lookup; deps через `config["configurable"]`; компиляция на импорте.
- **`PathTrace {branch, retry_cycles, nodes}`** — first-class domain-объект, единственный
  источник истины golden/CI-ассертов; `nodes` — информационное поле. Ассерты — только по
  `(branch, retry_cycles)`.
- **LiteLLM SDK-only** через `route(tier, …)` — единственный шов к LLM; тиры в `llm-tiers.yaml`
  (пин-гейт `-YYYY-MM-DD$`, цены токенов там же — контракт №5); `temperature=0` зашит в router.
  Дисциплина (правило 5) закреплена механическим тестом `tests/test_litellm_discipline.py`.
- **Кассеты**: `cassettes/<set>/`, ключ `(request_id, node, attempt)` — не хэш содержимого
  (контракт №4: смена промпта не рвёт replay — решение ловушки демо-регрессии iter 2). Формат
  хранит `usage` — per-node cost в iter 3–4. `replay` = $0 и дефолт; smoke-набор — авторский
  (`scripts/author_smoke_cassettes.py`, идемпотентный; `# aw-lite:` реальный record — iter 1).
- **MLflow ≥3.4** (slim-Compose, sqlite) — реестр появляется с iter 1 (Evaluation Dataset);
  в iter 0 только инфраструктура.

## Граница исполнения (Docker vs хост)

В Docker — только серверы наблюдаемости/реестра (MLflow, Langfuse, Prometheus/Grafana; Phoenix
исключён из проекта — ROADMAP → Заметки №5). Приложение, тесты, CI-гейты — на хосте через `uv run`. Контейнеры
**никогда не ходят в OpenAI**: весь LLM-egress — только с хоста, ключи в контейнеры не попадают.

## Слои `app/` (правило 6)

`cli` (тонкий транспорт) → `workflow` (граф-раннер, промпты, загрузка фикстур) →
`domain` (чистые функции/схемы, без I/O) + `persistence` (с iter 1); `llm/` — поперечное
(router/tiers/кассеты). `domain` не импортирует `app/*`-слои выше себя; зависимости —
аргументами; env — только через `Settings`.

## Сквозные конвенции (рубрика для ревью)

- env только `AW_*` через `Settings` (контракт №7); секреты — `SecretStr`, в код/логи не текут.
- `PathTrace` заморожен; новых веток/нод/полей не добавляем — масштаб числом заявок.
- Фикстуры — JSONL `{"id": "PA-<pack>-<NNN>", "text", "meta"}`, pack ∈ {smoke, base, post}.
- Потолок retry **N=2** (`AW_RETRY_LIMIT`) — зафиксирован до разметки golden (iter 1).
- `temperature=0` во всех нодах; record-прогоны только при temperature=0.
- Кассеты: replay никогда не бьёт в сеть, miss — громкая ошибка, не тихий фолбэк.
- Пиннинг: снапшоты моделей по дате; litellm/mlflow — версии в `uv.lock` (пин-гейт в тестах).
