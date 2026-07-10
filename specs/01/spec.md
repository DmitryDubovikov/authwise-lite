# Итерация 01 — trajectory golden-сет как артефакт реестра

> 🎯 Новая техника на старом стеке, минимальными затратами. Existence-gate, не accuracy-gate.

## Цель
Ввести технику **trajectory-as-artifact**: эталон — не финальный ответ, а путь по графу;
golden-сет путей становится версионируемым объектом реестра (MLflow Evaluation Dataset),
а не файлом в логах или DVC.

## 🧵 Красная нить (резюме)
> **Trajectory-as-artifact** (путь — версионируемый объект, не только промпт) — строка iter 1
> ROADMAP.

## Новая техника (и минимальный объём)
- **Trajectory golden-сет** — базовая пачка **30 заявок** (контракт №1: JSONL, pack=`base`) +
  разметка **допустимых путей**: запись = список `(branch, retry_cycles)`, ассерт — membership;
  **≥80% записей singleton** (правило 3), джокеры поимённо (см. Done-gate). Хранение —
  **MLflow Evaluation Dataset** (штатная сущность ≥3.4, sqlite-бэкенд поддерживает;
  expectations = допустимые пути). Каркас MLflow — из triagewise; ново только то, *что* лежит
  в реестре.

## Done-gate (по факту существования)
- `fixtures/requests-base.jsonl` — 30 заявок; **record-кассеты `cassettes/base/`** с реальным
  `usage` (гейтированный расход: cheap-тир, ≈$0.01 — спросить перед прогоном; закрывает
  `# aw-lite: авторские кассеты → реальный record` из iter 0).
- `fixtures/golden-base.jsonl` — source-of-truth разметки в репо: запись =
  `{request_id, allowed_paths: [{branch, retry_cycles}]}`; квота ≥80% singleton держится
  pytest-тестом; **джокеры поимённо: PA-base-027…030** (объективно неоднозначные заявки —
  фураж для champion/challenger-гейта, правило 3).
- `make golden-upload` **идемпотентен**: get-or-create датасета по имени + merge_records —
  повторный прогон не плодит ни датасеты, ни записи (стабильное состояние).
- `make golden-verify` — **verify в сторе, не в логах/UI** (правило 9): читает Evaluation
  Dataset через MLflow API, печатает записи с expectations, проверяет число записей (30) и
  квоту singleton по данным из стора.
- Ревью-пайплайн чист (CRITICAL/BUG = 0).

## Шаги
1. `mlflow>=3.4` в зависимости (пин в `uv.lock`); `app/persistence/golden.py` — репозиторий
   Evaluation Dataset (хендл открывается на boundary, workflow драйвера не знает).
2. `app/domain/golden.py` — схема разметки (`AllowedPath`, `GoldenRecord`) + membership-сравнение
   с `PathTrace` по `(branch, retry_cycles)` + функция квоты singleton; юнит-тесты.
3. Авторинг 30 заявок (`base`) с intended-путями + разметка `golden-base.jsonl`; тонкий
   транспорт — Make-таргеты (`record-base` — существующий CLI с env, `golden-upload`,
   `golden-verify`).
4. **Record-прогон пачки (спросить, ≈$0.01)** → реконсиляция intended vs фактический путь
   (replay, $0) → финальная разметка → upload + verify.
5. Ревью-пайплайн: general-reviewer ∥ constitution-reviewer → дедуп → review-auditor → фиксы
   CRITICAL/BUG → `/simplify` → точечные тесты (replay).

## Вне scope
CI path-gate и branch protection (iter 2) · «сломанный» policy-check и его кассеты (iter 2) ·
`RunRecord`-раннер батча (iter 2, контракт №3) · OTel/Langfuse (iter 3) · бюджет рана (iter 4) ·
«пострелизная» пачка (iter 5) · Prompt Registry / LoggedModel / alias (iter 6) · оценка
качества PA-решений (не accuracy-gate).
