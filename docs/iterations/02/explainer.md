# Итерация 02 — CI path-assertion gate / trajectory regression testing

> 🎯 **Цель проекта:** trajectory-eval — оценка *пути* многошагового агента, а не его финального
> ответа. Итерация 02 превращает эталон путей из iter 1 в **работающий регрессионный гейт**:
> pytest гоняет граф по golden-сету в replay и падает, если агент пошёл не по той ветке или
> накрутил не столько retry-циклов. Смена маршрута краснит CI — а через branch protection
> блокирует мёрдж.

## Зачем это (продукт и ценность)

Продукт (фикстура, но описываем как настоящий): payer **Northfield Health** маршрутизирует поток
Prior-Authorization-заявок — одобрить, дозапросить документы или эскалировать человеку — и держит
**сам маршрут** агента под операционным контролем. В iter 1 у команды появился эталон правильных
маршрутов в реестре; но эталон, с которым никто автоматически не сверяется, — это просто документ.
Ценность именно этой итерации в том, что теперь **любая правка, которая тихо меняет маршрут заявки,
ловится до мёрджа**. Инженер поправил промпт policy-check «чтобы был мягче» — и заявка, которую
раньше эскалировали человеку, вдруг проходит на автоодобрение: без гейта это уедет в прод незаметно
(текст ответа-то правдоподобный), а с гейтом CI краснеет с конкретной строкой «PA-base-021: ожидали
escalate ↻0, получили approve ↻0». Для ops-инженера payer'а это разница между «мы контролируем, куда
ходит агент» и «мы надеемся, что он ходит туда же, что вчера».

## 🧵 Что это дало резюме

Пункт north-star iter 2 — **CI path-assertion gate / trajectory regression testing** — стал
демонстрируемым. Доказательство: `tests/test_path_gate.py` гоняет граф по всем 30 golden-заявкам в
replay и ассертит **пройденную ветку + число retry-циклов** (не текст ответа); этот тест входит в
`make check`, который гоняет CI. А `make path-gate-broken` на нарочно «сломанном» наборе кассет даёт
**красный вердикт из-за смены маршрута** (3 регрессии), а не из-за отсутствия кассеты — ровно та
ловушка, которую north-star требует обойти.

## TL;DR (простыми словами)

Было (после iter 1): эталон путей лежит в реестре, но сверяется с ним только человек глазами.
Стало: есть автоматический **гейт маршрутизации**. Он прогоняет граф по базовой пачке из 30 заявок
(в replay, за $0), берёт фактический путь каждой и проверяет, что тот входит в список допустимых
путей из golden-разметки. Совпало у всех — зелено; у кого-то ветка или число retry-циклов уехали —
красно, с таблицей «ожидали X, получили Y». Гейт живёт в `make check` (значит и в CI), плюс есть
`make path-gate` — та же проверка, но печатает таблицу целиком (материал для витрины). Чтобы
доказать, что гейт реально ловит регрессию маршрута, рядом лежит нарочно «сломанный» набор кассет:
на нём гейт краснеет. Ещё появился общий раннер пачки `run_batch` — теперь и CLI, и тесты, и гейт
гоняют граф одним способом, а не каждый своим.

## Что это за техника

**Path-assertion gate (trajectory regression testing)** — это регрессионный тест не на *ответ*
агента, а на его *маршрут*. Обычный regression-тест ловит «функция стала возвращать другое число»;
path-assertion gate ловит «агент стал ходить по другой ветке графа». Мы собрали его на уже имеющемся
стеке нулём новых зависимостей: обычный pytest + чистая domain-функция сравнения. Движок ассертов
финализирован конституцией именно так (pytest + собственный membership), `agentevals` — отраслевой
референс, но его не тащим.

Ключевые термины, которыми оперируем дальше:
- **`PathTrace`** — типизированная запись пройденного пути: `{branch, retry_cycles, nodes}`. Источник
  истины для всех golden/CI-ассертов (правило 6): гейт сверяет именно её, а не телеметрию.
- **`RunRecord`** — единый артефакт батч-прогона: `{request_id, trace}`. Один раннер (`run_batch`)
  гонит пачку заявок через граф и отдаёт список `RunRecord`. Это тот самый «контракт №3» — его будут
  читать потребители следующих итераций (Prometheus iter 4, Phoenix iter 5, Prefect iter 7), а не
  гонять граф каждый по-своему.
- **membership-ассерт** — путь засчитан, если пара `(branch, retry_cycles)` входит в список
  `allowed_paths` golden-записи. Не exact-match по одной траектории: для объективно неоднозначных
  заявок («джокеров») в списке разрешено несколько путей.
- **cassette-miss vs смена маршрута** — две причины, по которым гейт мог бы покраснеть. Нам нужна
  только вторая. Если бы «сломанный» демо-набор ронял гейт из-за отсутствия кассеты
  (`FileNotFoundError`), красный CI доказывал бы не то. Поэтому ключ кассеты — `(request_id, node,
  attempt)`, он **не** зависит от текста промпта: смена промпта policy-check не рвёт replay, а лишь
  уводит путь с golden-ветки.

## Поток данных

Оператор (или CI-джоб) хочет узнать, ходит ли агент по-прежнему правильными маршрутами, и запускает
гейт — `make path-gate` (или `pytest tests/test_path_gate.py`). Дальше цепочка такая: чтобы было
что сравнивать, гейту нужны две вещи — фактические пути пачки и эталон. Фактические пути он получает,
прогнав пачку через граф; эталон читает из golden-разметки. Затем чистая функция сверяет одно с
другим и выносит вердикт.

```
make path-gate
      │
      ▼
scripts/path_gate.py  ── load_requests(requests-base.jsonl) ─┐  30 заявок
      │                └ load_golden(golden-base.jsonl) ──────┤  30 записей разметки
      │                                                       │
      ▼                                                       │
run_batch(requests)  ──► граф (LangGraph, replay $0) ──► [RunRecord{id, PathTrace}] × 30
      │                                                       │
      │  write_records(...) ──► runs/base.jsonl (JSONL-артефакт, gitignored — для iter 4/5/7)
      ▼                                                       ▼
build_gate_report(traces, golden)  ── membership по (branch, retry_cycles) ──►  GateReport
      │
      ├─ report.passed  ──► exit 0 (зелено)  /  exit 1 (регрессия маршрута)
      └─ report.render() ──► таблица «ожидаемый vs фактический путь» в лог (витрина)
```

Честные оговорки — что в этой итерации **не** происходит:
- **MLflow не участвует.** Гейт и раннер read-only по стору — они его вообще не открывают, всё
  гоняется офлайн в replay. Golden-разметку гейт читает из файла-фикстуры `fixtures/golden-base.jsonl`
  (тот же файл, что iter 1 заливает в Evaluation Dataset), а не из реестра. Так проще и это тот же
  источник истины; сверка гейта именно с реестром — не цель iter 2.
- **LLM не зовётся.** Всё в replay, $0. «Сломанный» набор кассет сочинён вручную (`# aw-lite:
  authored subset → real record`), а не записан живым сломанным промптом.
- **Branch protection ещё не включён.** Гейт краснит CI-джоб; но чтобы красный джоб *блокировал
  мёрдж*, нужно один раз включить branch protection на `main` через `gh` (см. `demo.md`, шаг с
  пометкой про подтверждение). Это меняет поведение push в `main`, поэтому вынесено в отдельный
  ручной шаг финала, а не в код.

| Инструмент / шаг | Что делает | Куда пишет |
|---|---|---|
| `run_batch` (`app/workflow/runner.py`) | гонит пачку заявок через граф в replay, собирает `PathTrace` каждой | возвращает `list[RunRecord]` в память |
| `write_records` (там же) | сериализует прогон в JSONL — артефакт для потребителей iter 4/5/7 | `runs/<cassette_set>.jsonl` (gitignored) |
| `build_gate_report` (`app/domain/gate.py`) | membership-сравнение путей пачки с golden-разметкой | возвращает `GateReport` (чистая функция, без I/O) |
| `scripts/path_gate.py` + `make path-gate` | транспорт: печатает таблицу «ожид vs факт», `exit≠0` при регрессии | stdout + exit-код |
| `tests/test_path_gate.py` | тот же гейт как pytest — входит в `make check` → в CI | pass/fail джоба |

## Слои и направление зависимостей

Гейт аккуратно ложится на швы правила 6 — чистое ядро в domain, прогон в workflow, транспорт снаружи:

```
transport   scripts/path_gate.py ─┐   app/cli/main.py ─┐        (тонкие адаптеры)
                                  │                     │
workflow    ────────────────────► run_batch / write_records (app/workflow/runner.py)
                                  │        │            │
domain      build_gate_report ◄───┘        │            │  render_path
            (app/domain/gate.py) ──uses──► path_allowed (app/domain/golden.py)
            PathTrace (app/domain/path.py) ◄── единственный источник истины ассертов
```

`domain/gate.py` не импортирует ничего из `app/workflow` или `app/cli` — только `domain/golden` и
`domain/path`. Прогон графа живёт этажом выше (`workflow/runner.py`), а `scripts/path_gate.py` — это
тонкий транспорт, который только склеивает загрузку фикстур, прогон и рендер.

## Карта «где в коде»

> Номера строк — ориентир на момент закрытия iter 2; надёжнее искать по именам символов.

1. **`RunRecord` + `run_batch` — единый артефакт батч-прогона** — `app/workflow/runner.py:19` и
   `:25`. `RunRecord` — это frozen-dataclass из `request_id` и `PathTrace`; в комментарии зафиксировано,
   что per-node usage/latency добавятся в iter 3/4, а здесь только путь. `run_batch` прогоняет всю
   пачку конкурентно через `asyncio.gather` и собирает записи в порядке пачки. Это консолидация: до
   iter 2 прогон дублировался в `cli/main` и в тестах, теперь он один.

   ```python
   @dataclass(frozen=True)
   class RunRecord:
       request_id: str
       trace: PathTrace  # источник истины golden/CI-ассертов (правило 6)

   async def run_batch(requests: list[PARequest], *, settings: Settings) -> list[RunRecord]:
       """Прогнать пачку через граф (в replay — $0) → RunRecord на заявку, в порядке пачки."""
       results = await asyncio.gather(*(run_pa_request(r, settings=settings) for r in requests))
       return [RunRecord(request_id=request.id, trace=result.trace)
               for request, result in zip(requests, results, strict=True)]
   ```

2. **JSONL-сериализация прогона** — `app/workflow/runner.py:58` (`write_records`) и `:65`
   (`read_records`). Пишет по одной заявке на строку, отсортированными ключами (стабильный diff), и
   умеет читать обратно. Смысл — не в самом гейте (он держит записи в памяти), а в том, чтобы у
   потребителей следующих итераций был готовый файловый артефакт прогона, а не необходимость снова
   гонять граф.

   ```python
   def write_records(records: list[RunRecord], path: Path) -> None:
       """JSONL-артефакт прогона (контракт №3) — его читают потребители следующих итераций."""
       path.parent.mkdir(parents=True, exist_ok=True)
       lines = (json.dumps(_to_dict(r), ensure_ascii=False, sort_keys=True) for r in records)
       path.write_text("\n".join(lines) + "\n")
   ```

3. **`build_gate_report` — сердце гейта (membership по пути)** — `app/domain/gate.py:70`. Чистая
   функция: на вход — словарь `{request_id: PathTrace}` фактических путей и список golden-записей; на
   выход — `GateReport`. Строки отчёта строятся **по golden-записям** (они — источник истины
   ожидаемого), а фактический путь без golden-записи попадает в `unexpected` (пачка разошлась с
   разметкой — тоже провал). Само сравнение делегируется `path_allowed` из iter 1.

   ```python
   def build_gate_report(traces: Mapping[str, PathTrace], golden: list[GoldenRecord]) -> GateReport:
       by_id = {g.request_id: g for g in golden}
       rows = tuple(_row(rid, record, traces.get(rid)) for rid, record in sorted(by_id.items()))
       unexpected = tuple(sorted(set(traces) - set(by_id)))
       return GateReport(rows=rows, unexpected=unexpected)
   ```

4. **`GateReport.passed` / `.render()` — вердикт и витрина** — `app/domain/gate.py:40` и `:43`.
   `passed` — единственный вход CI-гейта: зелено ⟺ нет регрессий и нет `unexpected`. `render()` рисует
   таблицу «ожид vs факт» для лога/витрины. Сравнение — только по пути `(branch, retry_cycles)`, текст
   ответа не смотрится вообще.

   ```python
   @property
   def passed(self) -> bool:
       return not self.regressions and not self.unexpected
   ```

5. **`tests/test_path_gate.py` — гейт как pytest (входит в `make check` → CI)** — четыре теста:
   базовая пачка (30) в replay проходит гейт; «сломанный» subset краснеет **из-за смены маршрута**
   (множество регрессий точно равно `REGRESSED`, а не «что-то упало»); контрольные заявки на том же
   сломанном наборе остаются зелёными (нет ложных срабатываний); JSONL round-trip. То, что тест
   *дошёл* до ассерта, само по себе доказывает, что replay нашёл кассеты (miss — громкая ошибка), а
   значит краснота — про маршрут.

   ```python
   def test_broken_set_regresses_on_route_change(broken_run):
       # дошли до ассерта → replay нашёл кассеты (miss = громкая ошибка) → краснота из-за МАРШРУТА
       report, _ = broken_run
       assert not report.passed
       assert {r.request_id for r in report.regressions} == REGRESSED
   ```

6. **`scripts/path_gate.py` + `make path-gate` — транспорт и витрина** — `scripts/path_gate.py:20`.
   Тонкий адаптер: грузит фикстуры, прогоняет `run_batch`, пишет JSONL-артефакт, печатает
   `report.render()` и выходит с кодом `0/1`. `--ids a,b,c` сужает пачку — так демонстрируется
   «сломанный» subset (`make path-gate-broken`).

   ```python
   records = asyncio.run(run_batch(requests, settings=settings))
   write_records(records, settings.runs_dir / f"{settings.cassette_set}.jsonl")
   report = build_gate_report({r.request_id: r.trace for r in records}, golden)
   print(report.render())
   raise SystemExit(0 if report.passed else 1)
   ```

7. **`scripts/author_broken_cassettes.py` — authored демо-регрессия ($0, идемпотентно)** —
   сочиняет набор `cassettes/base-broken-policy/` на 5 заявок: `classify` копируется из base как есть,
   а `policy-check` штампует всем `sufficient` (нарратив: «промпт потерял критерии»). Из-за этого путь
   уходит с golden-ветки: `PA-base-019` (ожидался `request-info ↻2`) и `PA-base-021` (ожидался
   `escalate ↻0`) сваливаются в `approve ↻0` — регрессия ветки; `PA-base-015` теряет retry-цикл. Две
   контрольные заявки (`001`, `003`) и так были `approve ↻0` — на них гейт остаётся зелёным.

   ```python
   def _sufficient() -> str:
       return PolicyCheckResult.model_validate(
           {"status": "sufficient", "missing": [], "rationale": _RATIONALE}
       ).model_dump_json()
   # ключ кассеты — (request_id, node, attempt): смена промпта НЕ рвёт replay (иначе cassette-miss)
   ```

8. **CI, Makefile, конфиг** — `.github/workflows/ci.yml` теперь после `make check` ещё гоняет
   `make path-gate` (таблица в лог); `Makefile` получил таргеты `author-broken-cassettes`,
   `path-gate`, `path-gate-broken`; `app/config.py:31` добавил `runs_dir` (gitignored) под
   JSONL-артефакты; `tests/conftest.py` вынес общий `replay_settings(cassette_set)` — офлайн-скелет
   Settings, чтобы env/.env не влияли на прогон, — им пользуются и smoke-, и path-gate-тесты.
