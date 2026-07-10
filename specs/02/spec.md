# Итерация 02 — CI path-assertion gate

> 🎯 Новая техника на старом стеке, минимальными затратами. Existence-gate, не accuracy-gate.

## Цель
Ввести **регрессионное тестирование маршрутизации**: pytest-гейт гоняет граф по golden-сету
в replay и ассертит **пройденный путь** (`branch` + `retry_cycles`), а не текст ответа. Смена
маршрута краснит CI и (через branch protection) блокирует мёрдж. Демо-регрессия — «сломанный»
policy-check со своим набором кассет — краснит гейт **из-за смены пути**, а не cassette-miss.

## 🧵 Красная нить (резюме)
Дословно из ROADMAP (строка iter 2): **«CI path-assertion gate / trajectory regression
testing»** — CI-джоб гоняет граф по golden-сету **в replay** и ассертит **пройденную ветку +
число итераций retry-loop**, не текст ответа; branch protection — красный CI реально блокирует
мёрдж; демо-регрессия: «сломанный» policy-check со своими record-кассетами — CI краснеет из-за
смены маршрута, а не cassette-miss.

## Новая техника (и минимальный объём)
- **Path-assertion gate (pytest + собственный membership-ассерт)** — движок финализирован
  (ROADMAP Заметки №2): pytest + `path_allowed` из domain, **ноль новых зависимостей**
  (agentevals — отраслевой референс, не тащим). Гейт = чистая domain-функция сравнения
  `RunRecord` пачки с golden-разметкой + pytest, который на ней падает.
- **`RunRecord` — единый артефакт батч-прогона (контракт №3)** — вводится здесь: один раннер в
  workflow-слое гонит пачку через граф и отдаёт `{request_id, path_trace}`. Консолидирует
  дублирование прогона (сейчас в `cli/main` и тестах). Per-node usage/latency **не** добавляем —
  скоуп iter 3/4 (помечено в коде). JSONL-сериализация — чтобы iter 4/5/7 читали артефакт.
- **Демо-регрессия — authored subset, $0** (решение пользователя): `cassettes/base-broken-policy/`
  — вручную сочинённый набор на 5–6 заявок, где policy-check отдаёт другой статус → путь уходит
  с golden-ветки. Помечен `# aw-lite: authored subset → real record`. Тест доказывает: гейт на
  этом наборе **падает** (регрессия маршрута, не cassette-miss).

## Done-gate (по факту существования)
- `make check` включает path-gate: базовая пачка (30) в replay → каждый `PathTrace` ∈
  golden `allowed_paths`; на `main` **зелёный** (проверено: пути точно матчат golden).
- Тест `test_broken_set_regresses`: та же пачка (subset) на `cassettes/base-broken-policy/` →
  гейт **падает**, причина — смена ветки (не FileNotFoundError кассеты).
- `make path-gate` печатает таблицу «ожидаемый vs фактический путь» и выходит с ненулевым кодом
  при регрессии (Витрина-материал).
- CI (`.github/workflows/ci.yml`) прогоняет гейт; branch protection на `main` требует его —
  включается `gh`-командой в конце (подтверждение пользователя, меняет поведение push в main).
- Ревью-пайплайн чист (CRITICAL/BUG = 0).

*Идемпотентность:* гейт и раннер — read-only по стору (стор не трогают, гоняют граф в replay);
`base-broken-policy` кассеты статичны в репо. Состояние стора не мутируется → повторный прогон
детерминирован без docker/сети.

## Шаги
1. `app/workflow/runner.py` — `RunRecord{request_id, trace}` + `run_batch(requests, settings)`
   + JSONL write/read. Переключить `cli/main` и `test_smoke_paths` на него (убрать дубль прогона).
2. `app/domain/gate.py` — чистая функция: `RunRecord`-ы пачки + golden-разметка → `GateReport`
   (строки ожидаемый/фактический + `passed`); рендер таблицы. Только membership по `PathTrace`.
3. `tests/test_path_gate.py` — happy-path гейт (base зелёный) + `base-broken-policy` красный
   (смена маршрута, не cassette-miss). `scripts/path_gate.py` + `make path-gate` — таблица + exit.
4. `scripts/author_broken_cassettes.py` (идемпотентный, $0) → `cassettes/base-broken-policy/`;
   CI: гейт в pytest уже внутри `make check`; задокументировать branch protection + `gh`-команду.
5. Ревью-пайплайн (general + constitution → auditor → фиксы → `/simplify`).

## Вне scope
- Per-node cost/latency в `RunRecord` (iter 3/4); Langfuse/OTel (iter 3); реальный record
  сломанного промпта (опц. поверх authored — деньги, гейтируется).
- Новые ветки/ноды/поля `PathTrace` (заморожен). Реестр промптов (iter 6). Правка golden-разметки.
- Accuracy PA-решений — гейт по существованию маршрута, не по «правильности» ответа.
