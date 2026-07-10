# Итерация 01 — trajectory golden-сет как артефакт реестра

> 🎯 **Цель проекта:** trajectory-eval — оценка *пути* многошагового агента, а не его финального
> ответа. Итерация 01 делает эталон путей **версионируемым объектом реестра**: golden-сет из
> 30 размеченных заявок заливается в MLflow как штатная Evaluation Dataset, а не лежит файлом
> в логах или под DVC.

## Зачем это (продукт и ценность)

Продукт (фикстура, но описываем как настоящий): payer **Northfield Health** маршрутизирует поток
Prior-Authorization-заявок — одобрить, дозапросить документы или эскалировать человеку — и держит
**сам маршрут** агента под операционным контролем. Бизнес-ценность всего проекта в том, что
ops-инженеру payer'а мало «агент однажды настроен и мы молимся»: ему нужен эталон путей, гейт
против регрессий маршрутизации, стоимость каждого шага, алерт на дрейф веток. Ценность именно
этой итерации: у команды впервые появляется **согласованный эталон правильных маршрутов** — по
каждой из 30 заявок зафиксировано, куда агент *обязан* её направить (approve сразу, approve после
одного до-запроса, эскалация, терминальный отказ после двух до-запросов), и этот эталон живёт не
в чьём-то ноутбуке, а в реестре — с версией, доступный всей команде и будущему CI-гейту. Без такого
эталона нечему краснеть, когда завтра правка промпта тихо уведёт заявку не туда.

## 🧵 Что это дало резюме

Пункт north-star iter 1 — **Trajectory-as-artifact** (путь как версионируемый объект реестра, не
только промпт) — стал демонстрируемым. Доказательство: `make golden-verify` читает **из самого
MLflow** Evaluation Dataset `pa-trajectory-golden-base` и печатает 30 заявок с их ожидаемыми путями
(ветка + число retry-циклов как expectations), а не финальные ответы. Эталон — это путь, и он лежит
в реестре как первоклассная сущность.

## TL;DR (простыми словами)

Было (после iter 0): граф умеет прогонять заявку и возвращать её путь, но «правильных» путей нигде
не записано — сравнивать не с чем. Стало: есть **базовая пачка из 30 PA-заявок** и рядом —
**разметка допустимых путей** для каждой (`fixtures/golden-base.jsonl`). Эта разметка заливается в
MLflow как Evaluation Dataset — штатное хранилище эталонов. Две команды: `make golden-upload`
(залить, идемпотентно — повторный прогон не плодит записи) и `make golden-verify` (прочитать
обратно из стора и показать, что 30 записей на месте и квота выдержана). Всё офлайн и за $0 —
LLM здесь не зовём вообще, это чистая работа с данными и реестром.

## Что это за техника

**Trajectory-as-artifact** — идея хранить как версионируемый эталон *путь агента по графу*, а не
его финальный ответ. У обычного eval эталон — «правильный ответ на вопрос»; здесь эталон —
«правильный маршрут заявки»: какая из трёх веток обязана сработать и сколько раз агент должен был
дозапросить документы.

**MLflow Evaluation Dataset** — штатная сущность MLflow (появилась в 3.x, пин `mlflow>=3.4`) для
наборов «входы → ожидаемые результаты», версионируемая как код в git и живущая на том же
sqlite-бэкенде, что уже поднят в slim-Compose. У каждой записи два блока: `inputs` (что подаётся
на вход — здесь id, текст заявки, досылаемые документы) и `expectations` (что ожидается — здесь
список допустимых путей). Мы не изобретали хранилище поверх реестра промптов — взяли готовую
сущность MLflow ровно под её задачу.

Ключевые термины, которыми оперируем дальше:
- **`GoldenRecord`** — разметка одной заявки: `{request_id, allowed_paths, note}`.
- **`allowed_paths`** — список допустимых путей, каждый путь — пара `(branch, retry_cycles)`.
  Ассерт — **membership**: фактический путь засчитан, если он входит в этот список. Exact-match по
  одной эталонной траектории считается хрупким (отраслевая практика trajectory-eval — допускать
  несколько reference-траекторий), поэтому список, а не одно значение.
- **singleton** — запись с ровно одним допустимым путём (= обычный exact-match). Правило 3
  конституции требует **≥80% записей singleton**, иначе разметка «размякает» — фактически 87%.
- **джокер** — запись с >1 допустимым путём: объективно неоднозначная заявка (у нас поимённо
  `PA-base-027…030`), где `note` обязан объяснить неоднозначность. Джокеры — не небрежность, а
  корм для будущего champion/challenger-гейта (iter 6): им есть что различать.

## Поток данных

Оператор хочет положить эталон путей в реестр и набирает `make golden-upload` (внутри —
`uv run python -m scripts.golden_upload`). Скрипт-транспорт тонкий: он спрашивает у `Settings`, где
лежат фикстуры и куда смотрит MLflow, читает две JSONL-фикстуры — `requests-base.jsonl` (30 заявок)
и `golden-base.jsonl` (их разметку) — и передаёт обе в workflow-функцию `upload_golden()`. Чтобы
эталон имел право попасть в стор, workflow сперва проверяет разметку на честность: она обязана
**биективно** накрывать пачку по `request_id` (ни лишних, ни недостающих заявок) и держать квоту
singleton ≥80% — иначе бросает ошибку и заливать нечего. Пройдя проверку, `build_dataset_records()`
собирает записи в формате Evaluation Dataset: `inputs` = то, что потребляет граф, `expectations` =
допустимые пути плюс `note`. Дальше единственный слой, знающий про MLflow-драйвер, —
`app/persistence/golden.py`: он делает **get-or-create** датасета по имени и `merge_records` —
поэтому повторная заливка апсертит те же 30 записей, а не плодит новые.

Затем оператор проверяет результат **в самом сторе** командой `make golden-verify`: та же
persistence-функция `fetch()` читает Evaluation Dataset обратно через MLflow API, поднимает каждую
строку в `GoldenRecord`, а workflow считает по данным *из стора* число записей, квоту singleton и
расхождения с пачкой (`missing`/`extra`). Печатается сам путь каждой заявки — не «alias существует»,
а `PA-base-019: request-info ↻2`.

```
оператор: make golden-upload
    │
    ▼
scripts/golden_upload.py  (транспорт, тонкий) ── Settings: где фикстуры, куда MLflow
    │  читает fixtures/requests-base.jsonl (30 заявок)
    │  читает fixtures/golden-base.jsonl   (30 разметок)
    ▼
app/workflow/golden.py :: upload_golden()
    │  build_dataset_records():
    │    • биекция request_id (пачка == разметка)   ← иначе ValueError
    │    • квота singleton ≥80%                       ← иначе ValueError
    │    • {inputs:{id,text,supplemental}, expectations:{allowed_paths,note}}
    ▼
app/persistence/golden.py :: upload()   ← единственный, кто знает MLflow-драйвер
    │  get-or-create датасета по имени + merge_records (апсерт по хэшу inputs)
    ▼
MLflow Evaluation Dataset  "pa-trajectory-golden-base"  (sqlite-бэкенд, :5051)


оператор: make golden-verify
    │
    ▼
app/persistence/golden.py :: fetch()  ── читает датасет обратно (to_df) → GoldenRecord
    │
    ▼
app/workflow/golden.py :: verify_golden()  ── число записей, квота, missing/extra ИЗ СТОРА
    │
    ▼
stdout:  PA-base-019: request-info ↻2  …  30 записей, singleton 87% → verify OK
```

| Инструмент | Что делает | Куда пишет |
|---|---|---|
| `scripts/golden_upload.py` (`make golden-upload`) | читает пачку + разметку, зовёт workflow-заливку | ничего своего — данные уходят в MLflow |
| `app/workflow/golden.py` | валидирует разметку (биекция + квота), собирает записи, оркеструет upload/verify | не знает MLflow-драйвер — зовёт persistence |
| `app/persistence/golden.py` | единственный слой с MLflow-драйвером: get-or-create + `merge_records`, `fetch` | MLflow Evaluation Dataset `pa-trajectory-golden-base` |
| MLflow (Docker, `make up`) | хранит Evaluation Dataset на sqlite-бэкенде | `mlflow-data/mlflow.db` (порт 5051) |
| `scripts/golden_verify.py` (`make golden-verify`) | читает датасет **из стора** и печатает пути + сводку | stdout (verify, правило 9) |

Честные оговорки: LLM в этой итерации **не зовётся вообще** — golden-сет собирается из фикстур и
разметки, никаких токенов. `PathTrace` здесь используется только как **тип** (пара
`(branch, retry_cycles)` в membership-ассерте) — граф по пачке в этой итерации не гоняется, это
скоуп iter 2 (CI path-gate: прогнать граф по golden-сету в replay и сравнить пройденный путь с
эталоном). Record-кассеты базовой пачки (`cassettes/base/`, 73 файла с реальным `usage`) записаны в
рамках этой итерации как плановый расход — они закрывают `# aw-lite: авторские кассеты → реальный
record` из iter 0 и понадобятся раннеру iter 2, но сам эталон путей от них не зависит.

Слои и направление зависимостей (правило 6 конституции — швы соблюдены):

```
scripts/golden_{upload,verify}.py  (транспорт, тонкий)
 └─► app/workflow/golden.py         (оркестрация: валидация разметки, сборка записей)
      ├─► app/domain/golden.py      (чистые функции: схемы, membership, квота — без I/O)
      └─► app/persistence/golden.py (MLflow-репозиторий — хендл через tracking_uri с boundary)
                │
                └─ env только через Settings (app/config.py, префикс AW_)
```

## Карта «где в коде»

Номера строк — ориентир на момент итерации; надёжнее искать по именам символов.

1. **Схема разметки и membership-ассерт** — `app/domain/golden.py`. Чистый domain-слой без I/O.
   `AllowedPath` — пара `(branch, retry_cycles)`; `GoldenRecord` — разметка одной заявки, чей
   валидатор `_honest_markup` запрещает дубли путей и джокера без объяснения. `path_allowed()` —
   и есть ассерт пути: фактический `PathTrace` засчитан, если пара входит в `allowed_paths`.
   `singleton_share()` считает долю singleton-записей для квоты.

   ```python
   class AllowedPath(BaseModel):
       branch: Branch
       retry_cycles: int = Field(ge=0)

   class GoldenRecord(BaseModel):
       request_id: str
       allowed_paths: list[AllowedPath] = Field(min_length=1)
       note: str = ""

       @model_validator(mode="after")
       def _honest_markup(self) -> "GoldenRecord":
           pairs = [(p.branch, p.retry_cycles) for p in self.allowed_paths]
           if len(pairs) != len(set(pairs)):
               raise ValueError(f"{self.request_id}: дубли в allowed_paths")
           if not self.is_singleton and not self.note:
               raise ValueError(f"{self.request_id}: джокер без note — неоднозначность не объяснена")
           return self

   def path_allowed(trace: PathTrace, record: GoldenRecord) -> bool:
       return any(
           p.branch == trace.branch and p.retry_cycles == trace.retry_cycles
           for p in record.allowed_paths
       )
   ```

2. **Сборка записей Evaluation Dataset + гейт честности разметки** — `app/workflow/golden.py`,
   функция `build_dataset_records()`. Прежде чем что-либо заливать, требует биективного покрытия
   пачки по `request_id` и квоты singleton — иначе бросает ошибку. Раскладывает заявку на `inputs`
   (что потребляет граф) и `expectations` (допустимые пути + `note`, благодаря которому запись
   стора потом поднимается обратно в `GoldenRecord`).

   ```python
   def build_dataset_records(requests, records) -> list[dict[str, Any]]:
       by_id = {g.request_id: g for g in records}
       if len(by_id) != len(records):
           raise ValueError("дубли request_id в golden-разметке")
       if {r.id for r in requests} != set(by_id):
           raise ValueError("golden-разметка не совпадает с пачкой заявок по request_id")
       share = singleton_share(records)
       if share < SINGLETON_QUOTA:
           raise ValueError(f"квота singleton нарушена: {share:.0%} < {SINGLETON_QUOTA:.0%}")
       return [
           {"inputs": {"request_id": request.id, "text": request.text,
                       "supplemental": request.supplemental},
            "expectations": {"allowed_paths": [p.model_dump() for p in by_id[request.id].allowed_paths],
                             "note": by_id[request.id].note}}
           for request in requests
       ]
   ```

3. **`verify_golden()` — сводка по данным ИЗ стора** — `app/workflow/golden.py`. Читает датасет
   через persistence, считает квоту и расхождения (`missing_ids` — есть в пачке, нет в сторе;
   `extra_ids` — сироты в сторе после правки inputs). `GoldenVerification.ok()` — единый вердикт
   verify: покрытие полное и квота держится. Это реализация правила 9 «verify the store, not the UI».

   ```python
   def verify_golden(*, tracking_uri: str, expected_ids: set[str]) -> GoldenVerification:
       records = golden_store.fetch(tracking_uri=tracking_uri)
       store_ids = {r.request_id for r in records}
       return GoldenVerification(
           records=records,
           singleton_share=singleton_share(records),
           missing_ids=frozenset(expected_ids - store_ids),
           extra_ids=frozenset(store_ids - expected_ids),
       )
   ```

4. **MLflow-репозиторий: единственный слой с драйвером** — `app/persistence/golden.py`. `upload()`
   идемпотентен благодаря get-or-create (`_dataset`: `get_dataset`, а на `RESOURCE_DOES_NOT_EXIST`
   — `create_dataset`) плюс `merge_records` (апсерт по хэшу inputs). `fetch()` читает датасет
   обратно и поднимает строки в domain-схему. `tracking_uri` приходит аргументом с boundary —
   слой не лезет в `Settings` сам (правило 6).

   ```python
   DATASET_NAME = "pa-trajectory-golden-base"

   def _dataset(name: str, tracking_uri: str) -> datasets.EvaluationDataset:
       mlflow.set_tracking_uri(tracking_uri)
       try:
           return datasets.get_dataset(name=name)
       except MlflowException as exc:
           if exc.error_code != "RESOURCE_DOES_NOT_EXIST":
               raise
           return datasets.create_dataset(name=name)

   def upload(records, *, tracking_uri, name=DATASET_NAME) -> None:
       _dataset(name, tracking_uri).merge_records(records)  # повторный прогон = no-op
   ```

5. **Разметка в репо — source of truth** — `fixtures/golden-base.jsonl` (30 строк). Запись =
   `{request_id, allowed_paths:[{branch, retry_cycles}], note?}`. 26 singleton + 4 джокера
   (`PA-base-027…030`), каждый с `note`, объясняющим неоднозначность. Рядом — сама пачка
   `fixtures/requests-base.jsonl` (30 PA-заявок, `pack=base`). Пример джокера:

   ```json
   {"request_id": "PA-base-030",
    "allowed_paths": [{"branch": "approve", "retry_cycles": 1}, {"branch": "request-info", "retry_cycles": 2}],
    "note": "джокер: CGM при basal-only инсулине — критерии на грани; после логов либо достаточно, либо документации так и не хватает"}
   ```

6. **Гейт разметки в pytest** — `tests/test_golden.py`. Держит контракт итерации офлайн:
   биективное покрытие пачки (`test_golden_covers_base_pack_bijectively`), квота singleton
   (`test_singleton_quota_holds`), джокеры — ровно поимённые (`test_jokers_are_exactly_the_named_ones`),
   membership-семантика ассерта, и — на **временном sqlite-сторе, без docker и сети** —
   идемпотентность двойной заливки:

   ```python
   def test_upload_is_idempotent(golden, requests, tmp_path) -> None:
       uri = f"sqlite:///{tmp_path}/mlflow.db"
       assert upload_golden(requests, golden, tracking_uri=uri) == 30
       assert upload_golden(requests, golden, tracking_uri=uri) == 30  # второй раз — не плодит
       verification = verify_golden(tracking_uri=uri, expected_ids={r.id for r in requests})
       assert len(verification.records) == 30
       assert verification.ok()
   ```

7. **Тонкий транспорт — Make-таргеты** — `scripts/golden_upload.py`, `scripts/golden_verify.py`,
   `Makefile` (`golden-upload`, `golden-verify`). Скрипты только читают `Settings`, зовут workflow
   и печатают; вся семантика — выше по слоям. `golden_verify.py` печатает сам путь каждой записи
   (`_render`: `approve ↻0 | escalate ↻0  [джокер]`) и падает `SystemExit`, если стор не сошёлся.
