# Итерация 04 — Agent FinOps guardrails: per-node SLO alerting + runtime budget controls

> 🎯 Единственный новый инструмент проекта (Prometheus + Grafana) + новая техника поверх
> старого каркаса. Existence-gate, не accuracy-gate.

## Цель
Превратить измерение iter 3 в **guardrails**: per-node метрики из `RunRecord` уходят в
Prometheus, Grafana-алерт называет просевшую ноду; retry-loop графа гейтится **остатком
бюджета рана в USD** — исчерпание становится маршрутом (`escalate`), а не исключением.

## 🧵 Красная нить (резюме)
Дословно из ROADMAP (строка iter 4): **«Agent FinOps guardrails: per-node SLO alerting +
runtime budget controls»** — per-node метрики (latency, cost, счётчик budget-эскалаций)
экспортируются в Prometheus; Grafana-дашборд по нодам + **alert rule на SLO-порог** (демо —
ужатый порог, replay); **retry-loop гейтится остатком бюджета рана: исчерпание → `escalate`**
(существующая ветка, новых полей `PathTrace` нет; дефолтный бюджет не меняет golden-пути,
демо — ужатый бюджет через env).

## Новая техника (и минимальный объём)
- **Runtime budget controls** (контракты №2, №5): `AW_RUN_BUDGET_USD` в `Settings`;
  `decide()` получает `budget_remaining_usd` и гейтит **только** ветку retry — would-retry при
  остатке ≤ 0 → `escalate`; approve/escalate/терминальный request-info не трогаются. Остаток
  считает `decide_node` (workflow): `cost_usd()` по `node_stats` из стейта, маппинг
  нода → тир — из `Settings`. Факт budget-эскалации — флаг в стейте → `RunRecord`
  (`budget_escalated`; `PathTrace` заморожен, не трогаем). Дефолт калибруется так, что
  golden-пути не меняются (path-gate зелёный); демо — ужатый бюджет через env.
- **Prometheus + Pushgateway** (решение 2026-07-10: батч-прогон — pull-модели скрейпить
  некого): `scripts/metrics_push.py` читает `runs/<set>.jsonl` (контракт №3 — читаем
  `RunRecord`, не гоняем граф) и пушит per-node агрегаты: latency (avg), cost (sum),
  счётчик вызовов, счётчик budget-эскалаций, число ранов. Cost — только `cost_usd()`
  (контракт №5), usage — из кассет.
- **Grafana provisioning-as-code + Grafana-managed alert** (решение 2026-07-10: Alertmanager
  не тащим — уведомления наружу не нужны, кадр витрины — Firing в Grafana UI): datasource,
  per-node дашборд и alert rule на SLO-порог латентности — YAML/JSON-файлы провижининга.
  В replay латентность ~0 → демо-порог ужат и помечен `# aw-lite:`.
- **Compose-профиль `slo`**: prometheus + grafana + pushgateway, версии запиннены; host-порты:
  Grafana 3002 (3000/3001 заняты), Prometheus 9090, Pushgateway 9091. Контейнеры в OpenAI не
  ходят (граница исполнения). `make up`/`obs-up` не тяжелеют.

## Done-gate (по факту существования)
- Ужатый бюджет через env уводит request-info-путь в `escalate` (CLI-кадр витрины);
  с дефолтным бюджетом path-gate по базовой пачке зелёный (golden-пути не изменились).
- `make slo-up` поднимает стек; `make replay-base` (пишет RunRecord) + `make metrics-push` →
  Prometheus отдаёт per-node latency/cost и счётчик budget-эскалаций.
- **Verify the store (правило 9):** скрипт запросом к Prometheus HTTP API видит per-node
  серии, к Grafana API — alert rule и её состояние Firing (не скрин UI).
- Grafana-дашборд бьёт latency/cost по нодам; alert rule на ужатом пороге реально Firing и
  называет просевшую ноду (label `node`).
- Идемпотентность: повторный `metrics-push` перезаписывает те же серии (last-write, без
  распухания); реестр MLflow не мутируется. `make check` зелёный без SLO-стека.
- Ревью-пайплайн чист (CRITICAL/BUG = 0).

## Шаги
1. Budget controls: `Settings.run_budget_usd` + `decide(..., budget_remaining_usd)` +
   расчёт остатка и флаг `budget_escalated` в `decide_node`/`RunRecord`; тесты domain/graph;
   калибровка дефолта (path-gate зелёный) + демо-команда с ужатым бюджетом.
2. `scripts/metrics_push.py` (RunRecord → Pushgateway, `prometheus-client`) + Makefile-цели.
3. Compose-профиль `slo` (пины) + провижининг Grafana: datasource, дашборд, alert rule.
4. `scripts/slo_verify.py` — verify через Prometheus/Grafana API (правило 9).
5. Ревью-пайплайн (general + constitution → auditor → фиксы → `/simplify`).

## Вне scope
- Alertmanager / нотификации наружу; стриминговый мониторинг (у нас batch-push).
- Phoenix/path-drift (iter 5); реестр промптов (iter 6); новые ветки/ноды/поля `PathTrace`.
- Никаких live/record-прогонов — только replay, $0; реальная калибровка SLO-порогов
  (existence-gate: порог демонстрационный).
