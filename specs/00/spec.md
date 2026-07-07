# Итерация 00 — каркас: control plane + branching-граф

> 🎯 Новая техника на старом стеке, минимальными затратами. Existence-gate, не accuracy-gate.

## Цель
Собрать каркас проекта переносом 1-в-1: control-plane скелет из triagewise-lite (uv/ruff/pytest,
`Settings`, `llm-tiers.yaml` + пин-гейт, `route()` + кассеты, Makefile, CI, slim-Compose
MLflow+sqlite) и граф-паттерн из policywise-lite (LangGraph, решение в ноде + тривиальный
routing, deps через `config["configurable"]`). Единственное новое — сам объект: граф PA-заявки
с настоящим branch-point и retry-циклом, возвращающий `PathTrace`.

## 🧵 Красная нить (резюме)
> **Branching-граф с реальным ветвлением заложен** (iter 0, ROADMAP).

## Новая техника (и минимальный объём)
- **Граф `classify → policy-check → decide{approve | request-info (retry ≤N=2) | escalate}`** —
  LLM в `classify`/`policy-check` (оба на `cheap`, temperature=0); `decide` — чистая
  domain-функция над структурированным выходом policy-check; retry-цикл возвращает в
  `policy-check` с инкрементом attempt. Граф-раннер возвращает `PathTrace {branch, retry_cycles,
  nodes}` (заморожен) вместе с ответом.
- **Кассеты по контракту №4** — `cassettes/<set>/` (env `AW_CASSETTE_SET`, дефолт `smoke`),
  ключ `(request_id, node, attempt)` — не хэш содержимого; формат хранит `usage` ответа
  (требование iter 3–4). Остальной каркас — перенос, не техника.

## Решения по ходу (зафиксированы с пользователем 2026-07-06)
- GitHub: публичный `DmitryDubovikov/authwise-lite` через `gh`; пуш — только по команде пользователя.
- Тиры: пины triagewise как есть + цены токенов в `llm-tiers.yaml` (контракт №5).
- Кассеты smoke — **авторские, $0** (record-прогоны запланированы только на iter 1/2/5,
  ROADMAP → Бюджет); `usage` в них синтетический, но формат боевой. `# aw-lite: авторские
  кассеты → реальный record в iter 1`.

## Done-gate (по факту существования)
- Репо: git + GitHub remote; Actions-скелет гоняет только `make check` — зелёный.
- `make check` локально зелёный (ruff + format-check + mypy + pytest, всё в `replay`).
- Smoke-фикстура 4 заявки (`fixtures/requests-smoke.jsonl`, контракт №1) покрывает все три
  терминала и retry-цикл: `approve` без retry, `↻1 → approve`, `escalate`,
  `↻2 → request-info` (терминальный). CLI печатает путь вида
  `classify → policy-check → request-info ↻2 → approve`; pytest-smoke ассертит
  `(branch, retry_cycles)` из `PathTrace`.
- `docker compose up mlflow` поднимает MLflow+sqlite (сущности — с iter 1).
- `docs/tech-decisions.md` заведён (сквозные конвенции, рубрика для ревью).
- Стор не мутируется → идемпотентность тривиальна; live-вызовов нет, бюджет итерации $0.
- Ревью-пайплайн чист (CRITICAL/BUG = 0).

## Шаги
1. Скелет: pyproject (uv, ruff, pytest, mypy; пины litellm/langgraph/mlflow ≥3.4), `Settings`
   (префикс `AW_`, контракт №7), Makefile, CI, compose, `llm-tiers.yaml`, `.env.example`,
   `docs/tech-decisions.md`.
2. `app/llm/`: `tiers.py` (пин-гейт снапшотов), `cassettes.py` (ключ/раскладка по контракту №4,
   `usage` в формате), `router.py` (`route()`, дисциплина LiteLLM: SDK-only, telemetry off,
   lazy import) + перенос механического теста дисциплины.
3. `app/domain/`: схемы (`PathTrace`, выход policy-check), `decide()` — чистая функция;
   `app/workflow/graph.py`: LangGraph-раннер (async boundary, deps через configurable);
   `app/cli/`: тонкий адаптер (прогон заявки, печать пути).
4. Smoke-фикстура + авторские кассеты + тесты (`replay`); GitHub-репо + push-готовность.
5. Ревью-пайплайн: general-reviewer ∥ constitution-reviewer → дедуп → review-auditor →
   фиксы CRITICAL/BUG → `/simplify` → точечные тесты.

## Вне scope
Golden-сет ~30 и MLflow Evaluation Dataset (iter 1) · CI path-gate и branch protection (iter 2) ·
OTel/Langfuse (iter 3) · Prometheus/Grafana, бюджет рана (iter 4; `AW_RUN_BUDGET_USD` в
Settings не заводим) · Phoenix (iter 5) · Prompt Registry / LoggedModel (iter 6) · record/live
прогоны · рендер PNG графа (витрина финала; путь открыт — `draw_mermaid_png()` у
скомпилированного графа).
