# Итерация 06 — Routing-policy as versioned artifact

> 🎯 Новая техника на старом стеке, минимальными затратами. Existence-gate, не accuracy-gate.

## Цель
Материализовать «routing-policy» как версионируемый артефакт реестра (решение «Г», CLAUDE.md →
Стек): промпты обеих LLM-нод версионируются в Prompt Registry, поверх — версия приложения
(external LoggedModel), пинящая их конкретные версии; alias `champion`/`challenger` + ручной
swap. Всё — штатный механизм MLflow 3, $0 (replay, реестр — локальный Compose).

## 🧵 Красная нить (резюме)
> **Routing-policy as versioned artifact** (application-версия пинит версии промптов) —
> existence-gate: промпты `classify`/`policy-check` в Prompt Registry; **LoggedModel-версия
> routing-policy пинит их конкретные версии**; alias `champion`/`challenger`; ручной swap;
> verify запросом к MLflow (правило 9).

## Новая техника (и минимальный объём)
- **Двухуровневое версионирование маршрутизирующего приложения** (проверено в песочнице,
  MLflow 3.14): `register_prompt` → `pa-classify` v1, `pa-policy-check` v1 (тексты из кода) и
  v2 (**rubber-stamp** — материализует нарратив демо-регрессии iter 2: «потерял критерии,
  штампует sufficient»; кассеты не нужны — ключ структурный, контракт №4);
  `create_external_model` → две версии `pa-routing-policy` с пинами в `params` +
  `link_prompt_version_to_model`; `register_model("models:/<id>")` → Model Registry, alias'ы
  на версиях: `champion` → v1 (classify v1 + policy-check v1), `challenger` → v2
  (classify v1 + policy-check v2). У LoggedModel собственных alias нет — alias живут на
  registered model, это штатный путь; swap = переназначение двух alias одной сущности.
- **Alias-загрузка (решение пользователя 2026-07-11):** opt-in env `AW_ROUTING_POLICY_ALIAS`
  (дефолт пуст = промпты из кода — CI/тесты offline не трогаем). CLI на boundary резолвит
  alias → LoggedModel → пины → шаблоны из Prompt Registry, печатает загруженные версии и
  передаёт `PromptBundle` в ран через `config` — workflow драйвер реестра не знает (правило 6).

## Done-gate (по факту существования)
- `make policy-seed` — **идемпотентен** (повторный прогон: версии не распухают, alias не
  дрейфуют — сид не трогает существующие alias, т.е. не откатывает swap).
- `make policy-verify` (правило 9, запросами к MLflow API): оба промпта в реестре; обе версии
  routing-policy пинят заявленные версии (params + `mlflow.linkedPrompts`); alias разрешаются.
- `make policy-swap` — champion ↔ challenger; `policy-verify` после swap показывает обмен;
  повторный swap возвращает исходное.
- `AW_ROUTING_POLICY_ALIAS=champion` + replay базовой пачки: CLI печатает
  `routing-policy: champion → ...`, шаблоны реально идут в ноды, пути пачки не меняются ($0).
- Ревью-пайплайн чист (CRITICAL/BUG = 0).

## Шаги
1. `app/persistence/routing_policy.py` — MLflow-драйвер: идемпотентный seed, `resolve(alias)`
   (версии + шаблоны), `swap()`; `Settings.routing_policy_alias`.
2. `PromptBundle` в `app/workflow/prompts.py` (дефолт — константы кода); прокидка через
   `config["configurable"]` в ноды графа; CLI-boundary: резолв alias + печать версий.
3. Скрипты-транспорты `policy_seed` / `policy_swap` / `policy_verify` + Make-таргеты
   (+ `replay-base-champion` для демо alias-загрузки).
4. Тесты (offline): sqlite-стор во временном каталоге — seed-идемпотентность, resolve, swap;
   replay-тест графа с кастомным `PromptBundle` (путь неизменен).
5. Ревью-пайплайн (general + constitution → дедуп → аудитор → фиксы → `/simplify`).

## Вне scope
Авто-промоушен/Prefect (iter 7 отменён); re-eval challenger / accuracy (existence-gate);
новые ветки/поля `PathTrace`; смена дефолтного источника промптов (код остаётся дефолтом,
CI-джоб не меняется); record-кассеты; UI-скрины (витрина — финал, правило 8).
