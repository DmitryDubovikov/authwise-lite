# Итерация 05 — path-distribution drift monitoring (PSI + Prom/Grafana)

> 🎯 Новая техника на старом стеке, минимальными затратами. Existence-gate, не accuracy-gate.

## Цель
Ввести технику **path-distribution drift monitoring**: мониторится сдвиг распределения
*маршрутов* (доли веток `approve`/`request-info`/`escalate`), а не качество ответа. Механика —
PSI поверх рельсов Prom/Grafana iter 4; Phoenix исключён (решение 2026-07-10, ROADMAP →
Заметки №5: Inferences вырезаны в v14, жили только in-process).

## 🧵 Красная нить (резюме)
> **Path-distribution drift monitoring** — «пострелизная» пачка ~30 заявок сгенерена +
> record-кассеты; **PSI по распределению веток** — чистая domain-функция; Grafana-панель
> показывает дрейф распределения веток (доля `escalate`/`request-info` растёт) между базовой
> (reference) и «пострелизной» (primary) пачкой + **alert rule на PSI-порог срабатывает честно**
> (сдвиг настоящий, порог 0.2 — отраслевой, не ужимаем) — строка iter 5 ROADMAP.

## Новая техника (и минимальный объём)
- **«Пострелизная» пачка** — 30 заявок (контракт №1: pack=`post`), сюжет сдвига: волна
  weight-loss/GLP-1-заявок (не покрываются → `escalate`) и наспех поданных заявок с документами,
  которые до-запрос не закрывает (→ терминальный `request-info`). Интент распределения:
  approve ~40% / escalate ~40% / request-info ~20% (база: ~73/13/13).
- **PSI** — чистая функция в domain (`branch_distribution` + `psi` со сглаживанием нулевых долей);
  пороги 0.1/0.2 — отраслевая конвенция, ассертов на точность нет (existence-gate).
- **Пуш и алертинг** — рельсы iter 4: `scripts/drift_push.py` читает ДВА RunRecord-артефакта
  (контракт №3: `runs/base.jsonl` = reference, `runs/post.jsonl` = primary), пушит
  `aw_branch_share{set,branch}` + `aw_path_drift_psi` в Pushgateway (идемпотентно, своя
  job-группа); Grafana — панель распределения веток base vs post + alert rule `PSI > 0.2`
  (as-code в `slo/`, как aw-slo).

## Done-gate (по факту существования)
- `fixtures/requests-post.jsonl` — 30 заявок; `cassettes/post/` — record-кассеты с `usage`
  (гейтированный расход ≈$0.01–0.02 — **одобрен 2026-07-10**); `make replay-post` → `runs/post.jsonl`.
- `make drift-push` (идемпотентен: замещение своей push-группы) → в Grafana видно распределение
  веток reference vs primary; alert rule на PSI-порог уходит в **Firing честно** — без ужатого
  порога.
- `make drift-verify` — verify the store (правило 9): серии `aw_branch_share` обоих сетов и
  `aw_path_drift_psi` из Prometheus API, состояние alert rule из Grafana API; UI — витрина.
- Ревью-пайплайн чист (CRITICAL/BUG = 0).

## Шаги
1. `app/domain/drift.py` (+ юнит-тесты): распределение веток по фиксированным терминалам
   контракта №2 и PSI со сглаживанием нулевых бинов.
2. Авторинг 30 post-заявок с intended-путями; **record-прогон (одобрен)** → реконсиляция
   intended vs фактический путь в replay; `runs/post.jsonl`.
3. `scripts/drift_push.py` + Make-таргеты (`record-post`, `replay-post`, `drift-push`,
   `drift-verify`); stdout — таблица долей и PSI (она же страховка витрины).
4. Grafana as-code: панель распределения веток + alert rule PSI; `scripts/drift_verify.py`.
5. Ревью-пайплайн: general-reviewer ∥ constitution-reviewer → дедуп → review-auditor → фиксы
   CRITICAL/BUG → `/simplify` → точечные тесты (replay).

## Вне scope
Golden-разметка post-пачки (трафик — не эталон; квота singleton не применяется) · CI-гейт на
дрейф (мониторинг ≠ ворота мёрджа) · стриминговый/«real-time» мониторинг (batch-пуш после
прогона) · Phoenix в любом виде · новые ветки/поля `PathTrace` · χ²-тест сверх PSI ·
registry-механика (iter 6) · Prefect (iter 7).
